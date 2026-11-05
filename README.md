# PertInfer Benchmark

Standalone task interfaces and independent evaluation for **PertInfer: Agentic
Inference of Human Perturbation Chains from Animal Mechanisms**.

Companion method: [PertInfer](https://github.com/DrHuang97/PertInfer).

This first extraction provides an installable benchmark toolkit, an offline
synthetic example, and tests. **It does not include the biological dataset or
historical experiments, predictions, logs, or result reports.** The example is an
engineering check, not a biological result or reproduction of the paper.

## Quick start

Python 3.10 or newer is required. The core toolkit has **no runtime Python
dependencies** and does not call a model or access the network.

```bash
git clone https://github.com/DrHuang97/PertInfer-Benchmark.git
cd PertInfer-Benchmark
python -m venv .venv
source .venv/bin/activate
python -m pip install .
pertinfer-benchmark demo --output demo-output
```

Use a fresh output directory on each run. The demo builds two explicitly
synthetic tasks, exports a reference-free input workspace, seals a run plan and
predictions, and writes `demo-output/scores.json` with six rows:

| Synthetic case | Exact fixture | Abstention | Missing run |
|---|---:|---:|---:|
| Complete reference | Containment 1 | Containment 0 | Containment 0 |
| Incomplete reference | Containment null | Containment null | Containment null |

The exact fixture uses hard-coded fictitious identities; it is a serialization
check, not a baseline method. A missing method arm is counted from the run plan
although it produced no files.

```bash
pertinfer-benchmark verify-release --release demo-output/release
pertinfer-benchmark verify-public --public demo-output/public
```

## Integrating an agent

The public Python API loads permitted inputs, validates graphs and exports
predictions. It does not import the evaluator. Methods receive an exported public
workspace; the evaluator separately receives the full release.

The [abstention example](examples/abstain.py) is a runnable third-party template:

```bash
python examples/abstain.py --public demo-output/public --output artifacts/abstention
pertinfer-benchmark score --release demo-output/release \
  --predictions artifacts/abstention --output artifacts/abstention-scores.json
```

See [the integration contract](docs/integration.md) for the run plan, output
format and version bindings. Pin the toolkit commit and dataset/input hashes.

## Building a dataset release

`build` packages explicit curator definitions. It does not infer orthologs,
generate human candidate mechanisms or curate references automatically.

```bash
pertinfer-benchmark build --spec examples/synthetic_spec.json --output artifacts/release
pertinfer-benchmark export-public --release artifacts/release \
  --view masked --output artifacts/public
```

The spec contains synthetic reference graphs and is for curators, not agent
input. This version supports synthetic, proxy and provisional tasks; it does not
admit independently qualified biological releases or report confirmatory metrics.

`build-materials` separately packages original local source bytes, extracted text,
section locators and receipts. PDF extraction needs Poppler's `pdftotext`.
See [materials](docs/materials.md) for the input format and current limits.

## Repository boundary

| Benchmark owns | Agent owns |
|---|---|
| Task and graph contracts | Molecular mapping strategies |
| Curator-supplied tasks, references and metadata | Human hypothesis-graph generation |
| Original-material packaging | Graph-directed search decisions and tool orchestration |
| Prediction export, run plans and consistency checks | Evidence interpretation and mechanism revision |
| Reference matching, graph size and aggregation | Prompts, model adapters and inference budgets |

The benchmark installs and runs without the agent. Scientific baseline adapters
are not migrated in this first extraction; the abstention template is an interface
example, not a substitute for those methods.

## Tests

```bash
python -m pip install '.[test]'
python -m pytest -q
```

Tests cover scientific matching, task averaging, missing/failed runs, incomplete
references, public input isolation, altered files and bindings, and original-material
provenance. CI also installs a wheel and runs the demo outside the checkout.

## Versions and limits

The graph format retains `path_transfer_v5.contract_v1`. The standalone package
uses a new envelope, `pertinfer_benchmark.release_v1`. **Historical development
seals are rejected, not rewritten.** Use the archived evaluator for those
experiments. See [migration and source provenance](docs/migration.md).

Hashes detect changes relative to recorded manifests. They do not prove chronology
or enforce operating-system isolation. Source text can itself contain answers;
public export alone does not establish blinding. Graph matching reflects declared
references and does not establish biological truth or completeness.

## License

Repository-authored software is released under the [MIT License](LICENSE).
Third-party research materials retain their own licenses and are not bundled here.
