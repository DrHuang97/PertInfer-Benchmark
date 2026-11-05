# PertInfer Benchmark

Benchmark and evaluation infrastructure accompanying **PertInfer: Agentic Inference of Human Perturbation Chains from Animal Mechanisms**.

Companion method: [PertInfer](https://github.com/DrHuang97/PertInfer).

## Status

This repository is initialized for the public benchmark release. Source-code and
data migration from the development project is pending. This initial commit is
not a runnable benchmark or a complete paper reproduction release.

## Scope

The benchmark repository will own:

- Task definitions, source provenance, material-library manifests and reference versions.
- Public task and graph schemas, validation and prediction export interfaces.
- Release and prediction manifests, content hashes and consistency verification.
- Evaluation metrics, scoring commands and baseline evaluation interfaces.
- Minimal examples and instructions for integrating third-party methods.

The benchmark must remain usable without installing the PertInfer method.
Molecular mapping strategies, hypothesis-graph generation, graph-directed search
decisions and evidence-based graph revision belong to the companion method.

## Integration boundary

The planned installable Python package will expose public task loading, graph
validation, prediction export and prediction sealing. PertInfer and other methods
will depend on a pinned benchmark version. Reference access and scoring run in a
separate evaluation stage after predictions are sealed. Hash manifests support
consistency checks; they do not by themselves enforce isolation or prove when a
prediction was made.

## Release preparation

- Migrate the benchmark implementation and its relevant tests.
- Package redistributable examples, dataset provenance and retrieval instructions.
- Document installation and an end-to-end minimal evaluation.
- Bind paper experiments to exact code, reference and material-library versions.

## License

Repository-authored software is released under the [MIT License](LICENSE).
Third-party datasets, papers and other research materials retain their own licenses;
the software license does not grant redistribution rights to those materials.
