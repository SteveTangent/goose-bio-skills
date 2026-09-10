#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run a bounded, explicitly configured local DESeq2 contrast; no installation."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile

VERSION = "0.9.2"
MAX_BYTES = 8 * 1024 * 1024
MAX_GENES = 30000
MAX_SAMPLES = 32
TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
FACTOR = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,63}\Z")

# All caller values are data in JSON/TSV, never interpolated into R code.
WORKER = r'''
args <- commandArgs(trailingOnly=TRUE)
fail <- function(status, code) {
  cat(paste("GOOSE_ERROR",status,code,sep="\t"),"\n",file=stderr(),sep="")
  quit(save="no",status=65L,runLast=FALSE)
}
if (!requireNamespace("DESeq2",quietly=TRUE) || !requireNamespace("jsonlite",quietly=TRUE))
  fail("needs-tool","missing-deseq2-or-jsonlite")
cfg <- jsonlite::fromJSON(args[1])
if (as.character(packageVersion("DESeq2")) != cfg$deseq2_version)
  fail("needs-tool","deseq2-version-mismatch")
tryCatch({
  counts <- read.delim(args[2],row.names=1,check.names=FALSE,quote="",comment.char="")
  meta <- read.delim(args[3],row.names=1,check.names=FALSE,quote="",comment.char="",colClasses="character")
  counts <- as.matrix(counts)
  storage.mode(counts) <- "integer"
  if (!identical(colnames(counts),rownames(meta))) fail("invalid-input","sample-order")
  meta$condition <- factor(meta$condition,levels=c(cfg$denominator,cfg$numerator))
  if (cfg$covariate != "") meta[[cfg$covariate]] <- factor(meta[[cfg$covariate]])
  terms <- c(if(cfg$covariate!="") cfg$covariate, "condition")
  formula <- reformulate(terms)
  design <- model.matrix(formula,meta)
  rank <- qr(design)$rank
  if (rank < ncol(design)) fail("invalid-input","rank-deficient-design")
  if (nrow(design)-rank < 1) fail("invalid-input","no-residual-df")
  keep <- rowSums(counts >= cfg$min_count) >= cfg$min_samples
  if (sum(keep) < 20) fail("invalid-input","too-few-retained-genes")
  counts <- counts[keep,,drop=FALSE]
  if (any(colSums(counts)==0)) fail("invalid-input","zero-depth-sample-after-filter")
  warnings <- character()
  result <- withCallingHandlers({
    dds <- DESeq2::DESeqDataSetFromMatrix(counts,meta,formula)
    dds <- DESeq2::DESeq(dds,fitType=cfg$fit_type,quiet=TRUE,
                        minReplicatesForReplace=Inf,parallel=FALSE)
    res <- DESeq2::results(dds,contrast=c("condition",cfg$numerator,cfg$denominator),
                         alpha=cfg$alpha,independentFiltering=cfg$independent_filtering,
                         cooksCutoff=cfg$cooks_cutoff,parallel=FALSE)
    table <- data.frame(gene_id=rownames(res),as.data.frame(res),check.names=FALSE,row.names=NULL)
    actual_fit <- attr(DESeq2::dispersionFunction(dds),"fitType")
    if (is.null(actual_fit) || actual_fit != cfg$fit_type)
      fail("invalid-output","dispersion-fit-changed")
    normalized <- DESeq2::counts(dds,normalized=TRUE)
    qc <- list(samples=colnames(counts),library_sizes=as.numeric(colSums(counts)),
       size_factors=as.numeric(DESeq2::sizeFactors(dds)),
       design_columns=colnames(design),design_rank=rank,residual_df=nrow(design)-rank,
       genes_input=length(keep),genes_retained=sum(keep),genes_filtered=sum(!keep),
       pvalue_missing=sum(is.na(res$pvalue)),padj_missing=sum(is.na(res$padj)),
       dispersion_fit=actual_fit,median_dispersion=median(DESeq2::dispersions(dds),na.rm=TRUE),
       automatic_outlier_replacement=FALSE,
       log_count_sample_distance=unname(as.matrix(dist(t(log2(normalized+1))))))
    list(results=table,qc=qc)
  },warning=function(w) {warnings <<- c(warnings,conditionMessage(w));invokeRestart("muffleWarning")})
  result$warnings <- unique(warnings)
  result$versions <- list(R=as.character(getRversion()),DESeq2=as.character(packageVersion("DESeq2")),
     jsonlite=as.character(packageVersion("jsonlite")),platform=R.version$platform)
  jsonlite::write_json(result,args[4],auto_unbox=TRUE,na="null",null="null",digits=16)
},error=function(e) fail("invalid-output","model-fit-failed"))
'''


class Failure(ValueError):
    def __init__(self, status, code):
        self.status, self.code = status, code
        super().__init__(code)


def fail(code, status="invalid-input"):
    raise Failure(status, code)


def safe_path(path):
    root = Path.cwd().resolve()
    if ".." in path.parts:
        fail("parent-traversal")
    absolute = path if path.is_absolute() else root / path
    try:
        relative = absolute.relative_to(root)
    except ValueError:
        fail("path-outside-working-directory")
    if not relative.parts:
        fail("empty-file-path")
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            fail("symlink-path")
    if not absolute.parent.is_dir():
        fail("missing-parent")
    return absolute


def read_bytes(path):
    path = safe_path(path)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    fd = os.open(path, flags)
    with os.fdopen(fd, "rb") as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_BYTES:
            fail("nonregular-or-oversized-input")
        data = handle.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        fail("oversized-input")
    return data


def table(data):
    try:
        rows = list(csv.reader(io.StringIO(data.decode("utf-8")),delimiter="\t",strict=True))
    except (UnicodeError,csv.Error):
        fail("invalid-utf8-tsv")
    if len(rows) < 2 or len(set(rows[0])) != len(rows[0]):
        fail("empty-table-or-duplicate-header")
    if any(len(row) != len(rows[0]) for row in rows) or any(not x for row in rows for x in row):
        fail("ragged-or-empty-field")
    return rows


def validate_inputs(count_data, meta_data, config):
    for key in ["numerator","denominator"]:
        if not isinstance(config[key],str) or not FACTOR.fullmatch(config[key]):
            fail("invalid-condition-label")
    if config["numerator"] == config["denominator"]:
        fail("identical-contrast-levels")
    cov = config["covariate"]
    if cov and (not FACTOR.fullmatch(cov) or cov in {"condition","sample_id"}):
        fail("invalid-covariate")
    if not math.isfinite(config["alpha"]) or not 0 < config["alpha"] < 1:
        fail("invalid-alpha")
    if not 1 <= config["min_count"] <= 2**31-1:
        fail("invalid-min-count")
    if config["fit_type"] not in {"parametric","local","mean"}:
        fail("invalid-fit-type")
    if not re.fullmatch(r"\d+\.\d+\.\d+",config["deseq2_version"]):
        fail("invalid-version")
    c, m = table(count_data), table(meta_data)
    if c[0][0] != "gene_id" or m[0][0] != "sample_id":
        fail("identifier-column")
    samples = c[0][1:]
    if not 4 <= len(samples) <= MAX_SAMPLES or not 20 <= len(c)-1 <= MAX_GENES:
        fail("matrix-dimensions")
    if not 1 <= config["min_samples"] <= len(samples):
        fail("invalid-min-samples")
    if any(not TOKEN.fullmatch(x) for x in samples + [r[0] for r in c[1:]]):
        fail("invalid-identifier")
    if len({r[0] for r in c[1:]}) != len(c)-1:
        fail("duplicate-gene")
    for row in c[1:]:
        if any(not re.fullmatch(r"0|[1-9][0-9]{0,9}",x) or int(x)>2**31-1 for x in row[1:]):
            fail("not-raw-integer-counts")
    if set(m[0]) != {"sample_id","condition"} | ({cov} if cov else set()):
        fail("metadata-columns-must-match-declared-design")
    ids = [r[0] for r in m[1:]]
    if len(ids) != len(set(ids)) or set(ids) != set(samples):
        fail("sample-set-mismatch")
    index = {r[0]:r for r in m[1:]}
    ordered = [index[s] for s in samples]
    condition_index = m[0].index("condition")
    labels = [row[condition_index] for row in ordered]
    if set(labels) != {config["numerator"],config["denominator"]}:
        fail("condition-levels")
    if min(labels.count(x) for x in set(labels)) < 2:
        fail("no-biological-replication")
    for row in ordered:
        if any(not FACTOR.fullmatch(row[i]) for i in range(1,len(row))):
            fail("invalid-factor")
    if cov and len({r[m[0].index(cov)] for r in ordered}) < 2:
        fail("constant-covariate")
    def render(rows):
        f=io.StringIO();csv.writer(f,delimiter="\t",lineterminator="\n").writerows(rows);return f.getvalue()
    return render(c),render([m[0]]+ordered),[r[0] for r in c[1:]],samples


def check_result(result, genes, samples, expected_retained):
    if not isinstance(result,dict) or not isinstance(result.get("results"),list):
        fail("missing-model-results","invalid-output")
    rows = result["results"]
    qc = result.get("qc",{})
    if qc.get("samples") != samples or len(rows) != qc.get("genes_retained") or qc.get("genes_input") != len(genes):
        fail("output-dimensions","invalid-output")
    ids=[r.get("gene_id") for r in rows]
    if not rows or ids != expected_retained:
        fail("output-gene-identities","invalid-output")
    if qc.get("genes_filtered") != len(genes)-len(expected_retained):
        fail("output-filter-count","invalid-output")
    factors = qc.get("size_factors")
    if not isinstance(factors,list) or len(factors) != len(samples) or any(
        not isinstance(x,(int,float)) or isinstance(x,bool) or not math.isfinite(x) or x<=0 for x in factors):
        fail("invalid-size-factors","invalid-output")
    columns={"gene_id","baseMean","log2FoldChange","lfcSE","stat","pvalue","padj"}
    for row in rows:
        if set(row)!=columns:fail("output-columns","invalid-output")
        for key in columns-{"gene_id"}:
            value=row[key]
            if value is not None and (isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value)):
                fail("nonfinite-output","invalid-output")
        for key in ["pvalue","padj"]:
            if row[key] is not None and not 0<=row[key]<=1:fail("pvalue-range","invalid-output")
        if row["baseMean"] is None or row["baseMean"]<0 or (row["lfcSE"] is not None and row["lfcSE"]<0):
            fail("invalid-model-scale","invalid-output")
    if not result.get("versions",{}).get("DESeq2"):
        fail("missing-version","invalid-output")


def publish(path, report):
    payload=(json.dumps(report,sort_keys=True,allow_nan=False,separators=(",",":"))+"\n").encode()
    if len(payload)>MAX_BYTES:fail("report-size-limit","invalid-output")
    path=safe_path(path)
    # Stage fully, then create a new hard link. No overwrite or destructive rollback.
    fd,stage=tempfile.mkstemp(prefix=".goose-de-",dir=path.parent)
    try:
        with os.fdopen(fd,"wb") as handle:
            handle.write(payload);handle.flush();os.fsync(handle.fileno())
        os.link(stage,path,follow_symlinks=False)
    finally:
        os.unlink(stage)


def run(args):
    output=safe_path(args.output)
    if output.exists():fail("output-exists","invalid-output")
    config={key:getattr(args,key) for key in ["numerator","denominator","covariate","alpha","min_count","min_samples","fit_type","deseq2_version"]}
    config.update(independent_filtering=args.independent_filtering=="enabled",cooks_cutoff=args.cooks_cutoff=="enabled")
    count_data,meta_data=read_bytes(args.counts),read_bytes(args.metadata)
    counts,meta,genes,samples=validate_inputs(count_data,meta_data,config)
    expected_retained=[row[0] for row in table(count_data)[1:]
        if sum(int(x)>=config["min_count"] for x in row[1:])>=config["min_samples"]]
    rscript=shutil.which(args.rscript)
    if not rscript:fail("rscript-not-found","needs-tool")
    rscript=Path(rscript).resolve(strict=True)
    if not rscript.is_file() or rscript.name != "Rscript":fail("invalid-rscript","needs-tool")
    with tempfile.TemporaryDirectory(prefix=".goose-de-work-",dir=Path.cwd()) as temporary:
        root=Path(temporary)
        (root/"worker.R").write_text(WORKER)
        (root/"counts.tsv").write_text(counts)
        (root/"samples.tsv").write_text(meta)
        (root/"config.json").write_text(json.dumps(config))
        # stdout and stderr go to private files instead of an unbounded memory pipe.
        with (root/"stdout.log").open("wb") as stdout,(root/"stderr.log").open("wb") as stderr:
            try:
                process=subprocess.run([str(rscript),"--vanilla","worker.R","config.json","counts.tsv","samples.tsv","result.json"],
                    cwd=root,stdout=stdout,stderr=stderr,timeout=120,check=False)
            except subprocess.TimeoutExpired:fail("model-timeout","needs-tool")
        if process.returncode:
            diagnostic=(root/"stderr.log").read_bytes()[:65536].decode("utf-8",errors="replace")
            match=re.search(r"GOOSE_ERROR\t([a-z-]+)\t([a-z-]+)",diagnostic)
            if match:fail(match[2],match[1])
            fail("rscript-failed","invalid-output")
        try:
            payload=read_bytes(root/"result.json")
            result=json.loads(payload)
        except (OSError,json.JSONDecodeError):fail("invalid-worker-result","invalid-output")
        check_result(result,genes,samples,expected_retained)
    report={"schema_version":"1.0","status":"completed","adapter_version":VERSION,
        "method":"DESeq2","config":config,"input_sha256":{"counts":hashlib.sha256(count_data).hexdigest(),"metadata":hashlib.sha256(meta_data).hexdigest()},
        "worker_sha256":hashlib.sha256(WORKER.encode()).hexdigest(),"rscript_sha256":hashlib.sha256(rscript.read_bytes()).hexdigest(),
        "network_performed":False,"model":result,"limitations":["One two-level contrast with at most one categorical adjustment; no interactions or continuous covariates.",
        "Automatic count replacement and fold-change shrinkage are not performed; missing p-values remain null.",
        "Input counts, biological replication, study design and interpretation require researcher review.",
        "Basic local execution evidence does not establish generalization, expert review or clinical validity."]}
    publish(output,report)
    return {"status":"completed","genes":len(result["results"]),"samples":len(samples),"version":VERSION}


def self_test():
    config=dict(numerator="treated",denominator="control",covariate="",alpha=.05,min_count=1,min_samples=2,fit_type="local",deseq2_version="1.52.0")
    counts=("gene_id\ta\tb\tc\td\n"+"".join(f"g{i}\t10\t12\t30\t32\n" for i in range(20))).encode()
    meta=b"sample_id\tcondition\nd\ttreated\nc\ttreated\nb\tcontrol\na\tcontrol\n"
    canonical=validate_inputs(counts,meta,config)
    assert canonical[1].splitlines()[1]=="a\tcontrol"
    cases=[(counts.replace(b"10",b"1.5",1),meta,config),(counts,meta.replace(b"a\tcontrol",b"z\tcontrol"),config),
        (counts,meta.replace(b"b\tcontrol",b"b\ttreated"),config),(counts,meta,{**config,"alpha":float("nan")}),
        (counts,meta,{**config,"numerator":"system('x')"}),(counts,meta,{**config,"covariate":"condition"}),
        (counts.replace(b"g1\t",b"g0\t"),meta,config),(counts,meta,{**config,"min_samples":5})]
    for c,m,cfg in cases:
        try:validate_inputs(c,m,cfg)
        except Failure:pass
        else:raise AssertionError("invalid input accepted")
    old=Path.cwd()
    with tempfile.TemporaryDirectory() as d:
        os.chdir(d)
        try:
            publish(Path("result.json"),{"status":"completed"})
            before=Path("result.json").read_bytes()
            try:publish(Path("result.json"),{"status":"different"})
            except FileExistsError:pass
            else:raise AssertionError("overwrite accepted")
            assert Path("result.json").read_bytes()==before
            Path("link").symlink_to("result.json")
            for p in [Path("link"),Path("../escape")]:
                try:read_bytes(p)
                except Failure:pass
                else:raise AssertionError("unsafe path accepted")
        finally:os.chdir(old)
    return {"status":"pass","version":VERSION,"checks":12,"scope":"stdlib input/output boundaries; model execution is separately tested"}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--self-test",action="store_true")
    for name in ["counts","metadata","output"]:p.add_argument("--"+name,type=Path)
    for name in ["numerator","denominator","deseq2-version"]:p.add_argument("--"+name)
    p.add_argument("--covariate",default="")
    p.add_argument("--rscript",default="Rscript")
    p.add_argument("--alpha",type=float)
    p.add_argument("--min-count",type=int)
    p.add_argument("--min-samples",type=int)
    p.add_argument("--fit-type",choices=["parametric","local","mean"])
    p.add_argument("--independent-filtering",choices=["enabled","disabled"])
    p.add_argument("--cooks-cutoff",choices=["enabled","disabled"])
    args=p.parse_args()
    try:
        if args.self_test:result=self_test()
        else:
            for name in ["counts","metadata","output","numerator","denominator","deseq2_version","alpha","min_count","min_samples","fit_type","independent_filtering","cooks_cutoff"]:
                if getattr(args,name) is None:fail("missing-"+name.replace("_","-"),"needs-decision")
            result=run(args)
        print(json.dumps(result,sort_keys=True));return 0
    except Failure as exc:
        print(json.dumps({"status":exc.status,"code":exc.code,"analysis_completed":False}),file=sys.stderr);return 2
    except OSError:
        print(json.dumps({"status":"io-error","code":"local-file-or-process-error","analysis_completed":False}),file=sys.stderr);return 3


if __name__=="__main__":
    raise SystemExit(main())
