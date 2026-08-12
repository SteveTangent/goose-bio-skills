# Contact and runtime boundaries

This reference defines the exact scope of
`protein-interface-contact-analysis` version `0.7.0`. The bundled helper is an
original, dependency-free implementation.

## Contact contract

- Input is one legacy fixed-column PDB coordinate file and two exact,
  distinct, nonblank one-character chain IDs.
- Both `ATOM` and `HETATM` records participate. A residue is identified by
  chain ID, residue name, integer residue sequence number, and insertion code.
  The helper does not infer polymer, ligand, solvent, or occupancy meaning.
- The element field in columns 77-78 is mandatory. H, D, and T atoms are
  excluded; no element is inferred from the atom name.
- Alternate-location indicators are refused instead of choosing a conformer.
  Files with more than one `MODEL` block are also refused.
- A residue pair is a contact when at least one retained cross-chain atom pair
  has Euclidean distance less than or equal to the declared cutoff. The report
  records the lexicographically deterministic minimum atom pair and distance.
- Contact geometry does not identify a biological assembly, prove binding, or
  establish affinity, conservation, causality, or function.

## Reviewed format source

| Surface | Reviewed source | Checked |
| --- | --- | --- |
| Legacy PDB `ATOM`/`HETATM` record names, chain, residue, coordinate, alternate-location, and element columns | [wwPDB PDB format 3.3 coordinate section](https://www.wwpdb.org/documentation/file-format-content/format33/sect9.html) | 2026-08-12 |

The source defines the syntax read by the helper; it does not validate this
package's biological interpretation.

## Safety and scale

The helper reads one stable regular non-symlink input, records its SHA-256, and
publishes one create-exclusive JSON file under the current directory through a
temporary file and hard link. It rejects parent traversal, paths outside that
root, and every symlink in the output-parent chain. It does not recurse,
decompress, use the network, or start subprocesses.
The fixed byte, line, coordinate, selected-record, and atom-comparison caps are
reported in every completed output. Unsupported scale returns `needs-tool`
without a partial report.

The pair scan is deliberately quadratic under the fixed comparison cap. A
spatial index is justified only if representative large interfaces exceed that
bounded preview contract.

## Exclusions and verification status

The package excludes mmCIF, ensemble or alternate-conformer analysis, residue
repair or renumbering, interface-area and solvent-accessibility calculations,
pocket detection, docking, molecular dynamics, affinity estimation, and
functional or clinical claims.

The deterministic self-test covers exact-cutoff inclusion, heavy-atom
filtering, `ATOM` and `HETATM` residues, sorted minimum-distance output,
determinism, invalid chain/cutoff, alternate-location and multiple-model
refusal, comparison caps, input-symlink refusal, output-root escape,
output-ancestor-symlink refusal, and no-overwrite publication. It is not agent
runtime evidence, a scientific benchmark, representative PDB validation, or
human-expert review. The package remains `preview + reviewed`.
