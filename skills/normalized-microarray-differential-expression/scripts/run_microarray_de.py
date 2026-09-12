#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Original, embedded I/O boundary: each exported helper remains standalone.
import argparse
import csv
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import stat
import sys
import tempfile

MAX_BYTES = 8 * 1024 * 1024


class UserError(ValueError):
    def __init__(self, code, message, status="invalid-input"):
        self.code, self.status = code, status
        super().__init__(message)


def require(condition, code, message, status="invalid-input"):
    if not condition:
        raise UserError(code, message, status)


def local_path(value):
    path = Path(value)
    root = Path.cwd().resolve()
    require(
        ".." not in path.parts,
        "parent-traversal",
        "Use a path within the working directory.",
    )
    path = path if path.is_absolute() else root / path
    require(
        path != root and path.is_relative_to(root),
        "outside-workspace",
        "Use a file or new output directory inside the working directory.",
    )
    current = root
    for part in path.relative_to(root).parts:
        current /= part
        require(
            not current.is_symlink(), "symlink-path", "Symlink paths are not accepted."
        )
    require(
        path.parent.is_dir(),
        "missing-parent",
        "Create the output parent directory first.",
    )
    return path


def read_local(value):
    path = local_path(value)
    fd = os.open(
        path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    )
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        require(
            stat.S_ISREG(before.st_mode) and before.st_size <= MAX_BYTES,
            "input-size-or-type",
            "Use a regular file of at most 8 MiB.",
        )
        data = stream.read(MAX_BYTES + 1)
        after = os.fstat(stream.fileno())
    require(
        len(data) <= MAX_BYTES
        and (before.st_ino, before.st_size, before.st_mtime_ns)
        == (after.st_ino, after.st_size, after.st_mtime_ns),
        "input-changed",
        "The input changed or exceeded its size limit.",
    )
    return data


def parse_json(data):
    def pairs(items):
        result = {}
        for key, value in items:
            require(
                key not in result, "duplicate-json-key", "JSON keys must be unique."
            )
            result[key] = value
        return result

    try:
        return json.loads(
            data,
            object_pairs_hook=pairs,
            parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)),
        )
    except (UnicodeError, ValueError, RecursionError) as exc:
        if isinstance(exc, UserError):
            raise
        raise UserError("invalid-json", "Use finite, valid UTF-8 JSON.") from exc


def read_json(value):
    data = read_local(value)
    return parse_json(data), hashlib.sha256(data).hexdigest()


def tsv(data):
    try:
        rows = list(
            csv.reader(io.StringIO(data.decode("utf-8")), delimiter="\t", strict=True)
        )
    except (UnicodeError, csv.Error) as exc:
        raise UserError("invalid-tsv", "Use a UTF-8 tab-separated table.") from exc
    require(
        len(rows) >= 2 and len(rows[0]) == len(set(rows[0])),
        "table-header",
        "A unique header and data rows are required.",
    )
    require(
        all(len(row) == len(rows[0]) for row in rows),
        "table-shape",
        "Every row must match the header.",
    )
    require(
        all(
            cell and len(cell) <= 256 and not any(ord(c) < 32 for c in cell)
            for row in rows
            for cell in row
        ),
        "table-cell",
        "Empty, oversized or control-character fields are not accepted.",
    )
    return rows


def encoded(value):
    return (
        json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, indent=2)
        + "\n"
    ).encode("utf-8")


def new_file(value, data):
    path = local_path(value)
    require(
        not path.exists(),
        "output-exists",
        "Choose a new output path; existing files are preserved.",
        "invalid-output",
    )
    require(
        len(data) <= 64 * 1024 * 1024,
        "output-size",
        "Output exceeds the bounded size.",
        "invalid-output",
    )
    fd, stage = tempfile.mkstemp(prefix=".goose-stage-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(stage, path, follow_symlinks=False)
    finally:
        os.unlink(stage)


def new_bundle(value, files):
    """Reserve a new directory exclusively; rollback only files we created."""
    path = local_path(value)
    require(
        not path.exists(),
        "output-exists",
        "Choose a new output directory.",
        "invalid-output",
    )
    require(
        files
        and all(
            re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,100}", name) for name in files
        ),
        "bundle-names",
        "Invalid output member.",
        "invalid-output",
    )
    require(
        sum(map(len, files.values())) <= 64 * 1024 * 1024,
        "output-size",
        "Output exceeds 64 MiB.",
        "invalid-output",
    )
    created = []
    with tempfile.TemporaryDirectory(prefix=".goose-stage-", dir=path.parent) as stage:
        for name, data in files.items():
            with (Path(stage) / name).open("xb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
        path.mkdir(mode=0o700, exist_ok=False)
        directory_id = path.stat().st_ino
        try:
            for name in files:
                target = path / name
                os.link(Path(stage) / name, target, follow_symlinks=False)
                created.append((target, target.stat().st_ino))
        except BaseException:
            if not path.is_symlink() and path.stat().st_ino == directory_id:
                for target, identity in created:
                    if (
                        not target.is_symlink()
                        and target.exists()
                        and target.stat().st_ino == identity
                    ):
                        target.unlink()
                try:
                    path.rmdir()
                except OSError:
                    pass
            raise


def base_checks():
    old = Path.cwd()
    with tempfile.TemporaryDirectory() as directory:
        os.chdir(directory)
        try:
            new_file("a.json", encoded({"value": 1}))
            before = Path("a.json").read_bytes()
            try:
                new_file("a.json", b"changed")
            except UserError:
                pass
            else:
                raise AssertionError("overwrite accepted")
            assert Path("a.json").read_bytes() == before
            Path("link").symlink_to("a.json")
            for path in ["link", "../outside"]:
                try:
                    read_local(path)
                except UserError:
                    pass
                else:
                    raise AssertionError("unsafe path accepted")
            for payload in [b'{"a":1,"a":2}', b'{"a":NaN}']:
                try:
                    parse_json(payload)
                except UserError:
                    pass
                else:
                    raise AssertionError("invalid JSON accepted")
            new_bundle("bundle", {"a.txt": b"a", "b.txt": b"b"})
            try:
                new_bundle("bundle", {"a.txt": b"changed"})
            except UserError:
                pass
            else:
                raise AssertionError("bundle overwritten")
            assert (Path("bundle") / "a.txt").read_bytes() == b"a"
        finally:
            os.chdir(old)
    return 6


def cli(run):
    try:
        result = run()
        print(json.dumps(result, sort_keys=True, ensure_ascii=False, allow_nan=False))
        return 0
    except UserError as exc:
        print(
            json.dumps(
                {
                    "status": exc.status,
                    "code": exc.code,
                    "message": str(exc),
                    "analysis_completed": False,
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 2
    except (KeyError, TypeError, AttributeError, IndexError) as exc:
        print(
            json.dumps(
                {
                    "status": "invalid-input",
                    "code": "unsupported-record-schema",
                    "message": "Check the input record shape and declared adapter version.",
                    "analysis_completed": False,
                }
            ),
            file=sys.stderr,
        )
        return 2
    except (OSError, ValueError) as exc:
        print(
            json.dumps(
                {
                    "status": "io-error",
                    "code": type(exc).__name__,
                    "analysis_completed": False,
                }
            ),
            file=sys.stderr,
        )
        return 3


VERSION = "0.12.0"
import shutil
import subprocess

# Original fixed worker. User strings are data, never R expressions.
WORKER = r'''
fail <- function(code) stop(paste0("GOOSE_ERROR:", code), call.=FALSE)
if (as.character(getRversion()) != "4.4.1" || !requireNamespace("limma", quietly=TRUE) || as.character(packageVersion("limma")) != "3.60.6") fail("runtime-version")
suppressPackageStartupMessages(library(limma))
cfg <- read.delim("config.tsv", stringsAsFactors=FALSE, check.names=FALSE)
get <- function(k) cfg$value[match(k,cfg$key)]
x <- as.matrix(read.delim("expression.tsv", row.names=1, check.names=FALSE))
m <- read.delim("samples.tsv", stringsAsFactors=FALSE, check.names=FALSE)
m$condition <- factor(m$condition, levels=c(get("denominator"),get("numerator")))
design <- model.matrix(~condition,m)
if (nzchar(get("covariate"))) {
  batch <- factor(m[[get("covariate")]])
  if (nlevels(batch)<2) fail("constant-covariate")
  design <- cbind(design,model.matrix(~batch)[,-1,drop=FALSE])
}
if (qr(design)$rank != ncol(design)) fail("confounded-design")
if (nrow(design)-ncol(design)<1) fail("no-residual-df")
fit <- lmFit(x,design)
if (!any(is.finite(fit$sigma) & fit$sigma>0)) fail("no-residual-variation")
fit <- eBayes(fit,trend=FALSE,robust=FALSE)
b <- fit$coefficients[,2]
se <- fit$stdev.unscaled[,2]*sqrt(fit$s2.post)
ci <- qt(.975,fit$df.total)*se
result <- data.frame(gene_id=rownames(x),baseMean=rowMeans(x),log2FoldChange=b,lfcSE=se,stat=fit$t[,2],pvalue=fit$p.value[,2],padj=p.adjust(fit$p.value[,2],method="BH"),ci_low=b-ci,ci_high=b+ci,check.names=FALSE)
if (any(!is.finite(as.matrix(result[,-1])))) fail("nonfinite-fit")
write.table(result,"results.tsv",sep="\t",row.names=FALSE,quote=FALSE)
pc <- prcomp(t(x),center=TRUE,scale.=FALSE,rank.=2)
if (sum(pc$sdev^2)<=0) fail("no-pca-variation")
pca <- data.frame(sample_id=m$sample_id,condition=m$condition,PC1=pc$x[,1],PC2=pc$x[,2])
write.table(pca,"pca.tsv",sep="\t",row.names=FALSE,quote=FALSE)
v <- pc$sdev[1:2]^2/sum(pc$sdev^2)*100
correlations <- cor(x)
correlations[!is.finite(correlations)] <- NA
write.table(data.frame(sample_id=colnames(x),correlations,check.names=FALSE),"correlations.tsv",sep="\t",row.names=FALSE,quote=FALSE,na="NA")
write.table(data.frame(rank=ncol(design),residual_df=nrow(design)-ncol(design),PC1_percent=v[1],PC2_percent=v[2]),"qc.tsv",sep="\t",row.names=FALSE,quote=FALSE)
'''


def text_field(value, label):
    require(isinstance(value,str) and 0<len(value)<=256 and not any(ord(c)<32 for c in value),
            "missing-"+label,"Declare "+label+" from the study or producer record.","needs-decision")
    return value


def table_bytes(rows):
    f=io.StringIO();csv.writer(f,delimiter="\t",lineterminator="\n").writerows(rows)
    return f.getvalue().encode()


def validate_inputs(raw, metadata, cfg):
    require(cfg["scale"]=="log2-normalized" and cfg["assay"]=="microarray",
            "assay-scale","Only already-normalized log2 microarray expression is supported.")
    require(cfg["independent_samples_declared"],"independence","Confirm independent biological samples.","needs-decision")
    for key in ["numerator","denominator","taxon","namespace","platform","normalization_provenance"]:
        text_field(cfg[key],key)
    require(cfg["feature_unit"] in {"probe","gene"},"feature-unit","Declare probe or gene rows.")
    require(cfg["numerator"]!=cfg["denominator"],"contrast","Declare distinct comparison levels.")
    require(math.isfinite(cfg["alpha"]) and 0<cfg["alpha"]<1,"alpha","Use alpha between zero and one.")
    rows=tsv(raw);meta=tsv(metadata)
    require(rows[0][0] in {"gene_id", "feature_id"}, "matrix-header", "Use feature_id or gene_id as the identifier column, retaining probe IDs when applicable.")
    samples=rows[0][1:]; ids=[r[0] for r in rows[1:]]
    require(4<=len(samples)<=32 and 20<=len(ids)<=30000 and len(set(ids))==len(ids),
            "matrix-dimensions","Use 20–30,000 unique features and 4–32 samples.")
    try: values=[[float(v) for v in r[1:]] for r in rows[1:]]
    except ValueError as exc: raise UserError("expression-values","Use finite log2 expression; resolve missing values upstream.") from exc
    require(all(math.isfinite(v) for row in values for v in row),"expression-values","Resolve missing or non-finite values upstream.")
    required={"sample_id","condition","subject_id"}
    cov=cfg["covariate"]
    require(not cov or cov not in required,"covariate","Use one separate categorical adjustment column.")
    require(set(meta[0])==required|({cov} if cov else set()),"metadata-columns","Supply sample_id, condition, subject_id and only the declared categorical adjustment.")
    records=[dict(zip(meta[0],r)) for r in meta[1:]]; lookup={r['sample_id']:r for r in records}
    require(len(lookup)==len(records) and set(lookup)==set(samples),"sample-mismatch","Metadata and expression samples must match exactly.")
    ordered=[lookup[s] for s in samples]
    require(len({r['subject_id'] for r in ordered})==len(samples),"repeated-subject","Paired or repeated subjects need another design; do not treat them as independent.")
    for r in ordered:
        require(all(v.lower() not in {'na','unknown','nan','null'} for v in r.values()),"unknown-metadata","Resolve unknown metadata before fitting.")
    labels=[r['condition'] for r in ordered]
    require(set(labels)=={cfg['numerator'],cfg['denominator']} and min(labels.count(v) for v in set(labels))>=2,
            "groups","Use two groups with at least two declared independent samples each; this is not a power guarantee.")
    if cov:
        by_batch={}
        for r in ordered: by_batch.setdefault(r[cov],set()).add(r['condition'])
        require(len(by_batch)>=2,"constant-covariate","The adjustment column must vary.")
        require(not all(len(v)==1 for v in by_batch.values()),"confounded-design","Condition cannot be separated from the declared categorical adjustment.")
    return rows,[meta[0]]+[[r[c] for c in meta[0]] for r in ordered],ids,samples


def run(a):
    require(a.expression and a.metadata and a.output,"input-paths","Supply expression, metadata and a new output directory.","needs-decision")
    cfg={k:getattr(a,k) for k in ['assay','scale','feature_unit','taxon','namespace','platform','normalization_provenance','numerator','denominator','covariate','alpha','independent_samples_declared']}
    require(cfg['alpha'] is not None,"alpha","Declare the multiple-testing threshold.","needs-decision")
    raw=read_local(a.expression); metadata=read_local(a.metadata)
    rows,meta,ids,samples=validate_inputs(raw,metadata,cfg)
    output=local_path(a.output)
    require(not output.exists(),"output-exists","Choose a new output directory.","invalid-output")
    runner=shutil.which(a.rscript)
    require(runner is not None,"rscript","Prepare R 4.4.1 and limma 3.60.6.","needs-tool")
    runner=Path(runner).resolve(strict=True)
    require(runner.is_file() and runner.name=='Rscript',"rscript","Select a trusted Rscript executable.","needs-tool")
    with tempfile.TemporaryDirectory(prefix='.goose-microarray-',dir=Path.cwd()) as directory:
        root=Path(directory)
        (root/'worker.R').write_text(WORKER)
        (root/'expression.tsv').write_bytes(table_bytes(rows));(root/'samples.tsv').write_bytes(table_bytes(meta))
        # Include only worker parameters; quoted TSV data never becomes R code.
        (root/'config.tsv').write_bytes(table_bytes([['key','value']]+[[k,cfg[k]] for k in ['numerator','denominator','covariate']]))
        with (root/'stdout.log').open('wb') as stdout,(root/'stderr.log').open('wb') as stderr:
            try:
                process=subprocess.run([str(runner),'--vanilla','worker.R'],cwd=root,stdout=stdout,stderr=stderr,timeout=120,check=False)
            except subprocess.TimeoutExpired as exc: raise UserError('model-timeout','R did not finish within 120 seconds.','needs-tool') from exc
        diagnostic=(root/'stderr.log').read_bytes()[:65536].decode(errors='replace')
        if process.returncode:
            match=re.search(r'GOOSE_ERROR:([a-z-]+)',diagnostic)
            code=match[1] if match else 'worker-failed'
            raise UserError(code,'Inspect the declared design and pinned local R environment.','needs-tool' if code=='runtime-version' else 'invalid-output')
        rr=tsv(read_local(root/'results.tsv'))
        keys=['gene_id','baseMean','log2FoldChange','lfcSE','stat','pvalue','padj','ci_low','ci_high']
        require(rr[0]==keys and [r[0] for r in rr[1:]]==ids,"result-identities","Worker results must retain every feature in order.","invalid-output")
        results=[]
        for r in rr[1:]:
            vals=[float(x) for x in r[1:]]
            require(all(math.isfinite(x) for x in vals) and vals[2]>=0 and all(0<=x<=1 for x in vals[4:6]),"result-values","Invalid model statistics.","invalid-output")
            results.append(dict(zip(keys,[r[0]]+vals)))
        qr=tsv(read_local(root/'qc.tsv')); q=dict(zip(qr[0],[float(x) for x in qr[1]]))
        require(q['rank']<len(samples) and q['residual_df']>0,"result-design","Invalid fitted design.","invalid-output")
        files={name:read_local(root/name) for name in ['results.tsv','pca.tsv','correlations.tsv']}
    qc={'samples':samples,'genes_input':len(ids),'genes_retained':len(ids),'genes_filtered':0,
        'pvalue_missing':0,'padj_missing':0,'design_rank':int(q['rank']),'residual_df':int(q['residual_df']),
        'pca_variance_percent':[q['PC1_percent'],q['PC2_percent']]}
    qc['groups']={g:sum(v[meta[0].index('condition')]==g for v in meta[1:]) for g in [cfg['denominator'],cfg['numerator']]}
    report={'schema_version':'1.0','status':'completed','tool':{'name':'goose_microarray_limma','version':VERSION},
            'method':'limma-microarray','config':cfg,'input_sha256':{'expression':hashlib.sha256(raw).hexdigest(),'metadata':hashlib.sha256(metadata).hexdigest()},
            'runtime_versions':{'R':'4.4.1','limma':'3.60.6','python':sys.version.split()[0]},
            'worker_sha256':hashlib.sha256(WORKER.encode()).hexdigest(),'network_performed':False,
            'model':{'results':results,'qc':qc},'warnings':([{'code':'limma-warning','message':diagnostic.strip()}] if diagnostic.strip() else []),
            'files':['de.json',*files], 'output_sha256':{k:hashlib.sha256(v).hexdigest() for k,v in files.items()},
            'limitations':['Rows retain the declared probe or gene unit; no automatic probe collapsing or identifier conversion.',
                'Unadjusted PCA and correlations describe the supplied normalized log2 matrix, not batch correction or automatic sample exclusion.',
                'One independent two-group contrast and at most one categorical adjustment; no paired designs, interactions, missing-value imputation or re-normalization.',
                'baseMean is average log2 expression, stat is moderated t, and confidence limits are pointwise 95% intervals; BH is across all supplied features.',
                'Scale, platform, independence and normalization provenance are declarations that require review; a completed model is not biological validation.']}
    payload=encoded(report)
    require(len(payload)<=MAX_BYTES,"result-size","Model JSON exceeds 8 MiB; use the documented external-result route.","invalid-output")
    files['de.json']=payload;new_bundle(a.output,files)
    return {'status':'completed','features':len(ids),'samples':len(samples),'version':VERSION}


def self_test():
    n=base_checks()
    rows=[['gene_id','a','b','c','d']]+[[f'p{i}','5.2','5.3','6.1','6.4'] for i in range(20)]
    meta=[['sample_id','condition','subject_id'],['d','treated','d'],['c','treated','c'],['b','control','b'],['a','control','a']]
    cfg=dict(assay='microarray',scale='log2-normalized',feature_unit='probe',taxon='9606',namespace='probe-id',platform='synthetic',normalization_provenance='synthetic',numerator='treated',denominator='control',covariate='',alpha=.05,independent_samples_declared=True)
    out=validate_inputs(table_bytes(rows),table_bytes(meta),cfg);assert out[1][1][0]=='a'
    cases=[(rows,meta,{**cfg,'scale':'TPM'}),(rows,meta,{**cfg,'assay':'RNA-seq'}),
           (rows,meta,{**cfg,'independent_samples_declared':False}),(rows,meta,{**cfg,'numerator':'control'}),
           (rows,meta[:-1],cfg),(rows,[meta[0]]+[r[:2]+['same'] for r in meta[1:]],cfg),
           (rows[:2]+rows[1:],meta,cfg),(rows,meta,{**cfg,'alpha':float('nan')})]
    for r,m,c in cases:
        try: validate_inputs(table_bytes(r),table_bytes(m),c)
        except UserError: pass
        else: raise AssertionError('invalid scientific input accepted')
    return {'status':'pass','version':VERSION,'checks':n+1+len(cases),'scope':'deterministic input/output checks; R execution recorded separately'}


def main():
    p=argparse.ArgumentParser(description='Fit one independent contrast in already-normalized log2 microarray expression with limma.')
    p.add_argument('--self-test',action='store_true')
    for key in ['expression','metadata','output','assay','scale','feature-unit','taxon','namespace','platform','normalization-provenance','numerator','denominator']:
        p.add_argument('--'+key)
    p.add_argument('--covariate',default='');p.add_argument('--alpha',type=float)
    p.add_argument('--rscript',default='Rscript');p.add_argument('--independent-samples-declared',action='store_true')
    a=p.parse_args()
    return self_test() if a.self_test else run(a)


if __name__=='__main__':
    raise SystemExit(cli(main))
