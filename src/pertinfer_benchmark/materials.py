#!/usr/bin/env python3
"""Build an offline material corpus from a versioned list of original files.

No network, LLM, answer graphs, or prior solver reports are read. Input spec is a
curation artifact: each source requires its original URL and expected SHA256.
"""
import argparse
import hashlib
import json
import re
import subprocess
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree as ET


class VisibleHTML(HTMLParser):
    def __init__(self):
        super().__init__(); self.hidden = 0; self.parts = []
    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"): self.hidden += 1
    def handle_endtag(self, tag):
        if tag in ("script", "style"): self.hidden = max(0, self.hidden - 1)
        if tag in ("p", "div", "tr", "h1", "h2", "h3", "li"): self.parts.append("\n")
    def handle_data(self, data):
        if not self.hidden: self.parts.append(data)


def text_of(element):
    return "" if element is None else re.sub(r"\s+", " ", " ".join(element.itertext())).strip()


def extract(path, fmt):
    """Return original-source text, addressable sections, and raw source aliases."""
    aliases = []
    if fmt == "xml":
        tree = ET.fromstring(path.read_bytes())
        sections = []
        for index, element in enumerate(tree.iter()):
            if element.tag in ("abstract", "sec", "fig", "table-wrap", "supplementary-material"):
                sid = element.get("id") or f"{element.tag}-{index}"
                title = text_of(element.find("title")) or text_of(element.find("label")) or sid
                sections.append({"id": sid, "title": title, "text": text_of(element)})
        # Index actual body paragraphs that explicitly cite a figure. Keep the
        # link and original paragraph locator; never copy the entire article to
        # every figure or generate image labels from a solver's interpretation.
        parents = {child: parent for parent in tree.iter() for child in parent}
        figure_ids = {fig.get("id") for fig in tree.iter("fig") if fig.get("id")}
        used_ids = {s["id"] for s in sections}
        for index, paragraph in enumerate(tree.findall(".//body//p"), 1):
            ancestors = []; parent = parents.get(paragraph)
            while parent is not None:
                ancestors.append(parent); parent = parents.get(parent)
            if any(x.tag in ("fig", "table-wrap", "supplementary-material") for x in ancestors):
                continue
            cited = sorted({rid for ref in paragraph.iter("xref") if ref.get("ref-type") == "fig"
                            for rid in ref.get("rid", "").split() if rid in figure_ids})
            if not cited:
                continue
            sid = paragraph.get("id") or f"body-p-{index}"
            while sid in used_ids:
                sid += "-paragraph"
            used_ids.add(sid)
            parent_section = next((x for x in ancestors if x.tag == "sec"), None)
            sections.append({"id": sid, "title": text_of(parent_section.find("title")) if parent_section is not None else "Body paragraph",
                "text": text_of(paragraph), "referenced_figures": cited,
                "xml_locator": f"body//p[{index}]", "parent_section": parent_section.get("id") if parent_section is not None else None})
        return text_of(tree), sections, aliases
    if fmt == "json":
        data = json.loads(path.read_text())
        # Alias sets come from original UniProt identity metadata, not gold mappings.
        for row in data.get("results", []) if isinstance(data, dict) else []:
            if not isinstance(row, dict) or not row.get("primaryAccession"):
                continue
            acc = row["primaryAccession"]
            group = {acc, "UniProt:" + acc}
            for gene in row.get("genes", []):
                name = gene.get("geneName", {}).get("value")
                if name: group.update([name, "symbol:" + name])
                for synonym in gene.get("synonyms", []):
                    if synonym.get("value"): group.add(synonym["value"])
            for cross_reference in row.get("uniProtKBCrossReferences", []):
                if cross_reference.get("database") == "Ensembl":
                    for prop in cross_reference.get("properties", []):
                        if prop.get("key") == "GeneId" and isinstance(prop.get("value"), str):
                            gene_id = prop["value"]
                            group.update([gene_id, gene_id.split(".", 1)[0], "Ensembl:" + gene_id.split(".", 1)[0]])
            description = row.get("proteinDescription", {})
            for name in [description.get("recommendedName", {})] + description.get("alternativeNames", []):
                if name.get("fullName", {}).get("value"): group.add(name["fullName"]["value"])
                group.update(x["value"] for x in name.get("shortNames", []) if x.get("value"))
            aliases.append(sorted(group))
        for row in data.get("molecules", []) if isinstance(data, dict) else []:
            group = {str(row[k]) for k in ("molecule_chembl_id", "pref_name") if row.get(k)}
            for synonym in row.get("molecule_synonyms", []):
                group.update(str(synonym[k]) for k in ("molecule_synonym", "synonyms") if synonym.get(k))
            if group: aliases.append(sorted(group))
        text = json.dumps(data, ensure_ascii=False, indent=2)
        return text, [{"id": "full", "title": "Original JSON response", "text": text}], aliases
    if fmt == "html":
        parser = VisibleHTML(); parser.feed(path.read_text(errors="replace"))
        text = re.sub(r"[ \t]+", " ", "".join(parser.parts))
        text = re.sub(r"\n\s*\n+", "\n", text).strip()
        return text, [{"id": "full", "title": "Original HTML visible text", "text": text}], aliases
    if fmt == "pdf":
        raw = path.read_bytes()
        if not raw.startswith(b"%PDF") or b"%%EOF" not in raw[-2048:]:
            raise ValueError("PDF header/EOF integrity failure: " + str(path))
        proc = subprocess.run(["pdftotext", "-layout", str(path), "-"], capture_output=True, check=True, timeout=60)
        text = proc.stdout.decode("utf-8")
        sections = [{"id": f"page-{i}", "title": f"PDF page {i}", "text": page} for i, page in enumerate(text.split("\f"), 1) if page.strip()]
        return text, sections, aliases
    if fmt == "image":
        return "", [], aliases
    text = path.read_text()
    return text, [{"id": "full", "title": "Original text", "text": text}], aliases


def build(spec, destination):
    root = Path(destination).resolve()
    root.mkdir(parents=True, exist_ok=False)
    (root / "assets").mkdir()
    materials = []; aliases = list(spec.get("entity_aliases", [])); receipts = []
    for source in spec["sources"]:
        raw = Path(source["path"]).read_bytes()
        sha = hashlib.sha256(raw).hexdigest()
        if sha != source["sha256"] or not source.get("source_url"):
            raise ValueError("Original source URL/hash missing or mismatched: " + source["material_id"])
        suffix = {"xml": ".xml", "json": ".json", "html": ".html", "pdf": ".pdf", "image": ".jpg"}.get(source["format"], ".txt")
        relative = "assets/" + sha + suffix
        path = root / relative; path.write_bytes(raw)
        text, sections, groups = extract(path, source["format"])
        aliases.extend(groups)
        materials.append({"material_id": source["material_id"], "title": source["title"], "source_url": source["source_url"],
            "source_kind": source.get("source_kind", source["format"]), "scope": source.get("scope", "Original public source; determine experimental applicability from the source"),
            "text": text, "sections": sections, "artifacts": [{"path": relative, "mime_type": source["mime_type"], "sha256": sha, "bytes": len(raw)}]})
        receipts.append({k: source[k] for k in ("material_id", "source_url", "sha256", "retrieved_at") if k in source})
    by_id = {m["material_id"]: m for m in materials}
    for source in spec["sources"]:
        if source.get("caption_from"):
            ref = source["caption_from"]
            sec = next(s for s in by_id[ref["material_id"]]["sections"] if s["id"] == ref["section"])
            m = by_id[source["material_id"]]
            m["text"] = sec["text"]
            m["sections"] = [{"id": "caption", "title": sec["title"], "text": sec["text"],
                "source_locator": {"material_id": ref["material_id"], "section": ref["section"]}, "retrieval_scope": "Original figure caption"}]
            for paragraph in by_id[ref["material_id"]]["sections"]:
                if ref["section"] in paragraph.get("referenced_figures", []):
                    m["sections"].append({"id": "body-reference-" + paragraph["id"], "title": paragraph["title"], "text": paragraph["text"],
                        "source_locator": {"material_id": ref["material_id"], "section": paragraph["id"], "figure_id": ref["section"],
                            "xml_locator": paragraph["xml_locator"], "relation": "body_paragraph_explicitly_cites_figure"},
                        "retrieval_scope": "Original body text citing this figure; not image OCR or visual verification"})
    corpus = {"schema": "graph_process_material_corpus_v1", "corpus_id": spec["corpus_id"], "task_id": spec["task_id"],
        "construction": spec.get("construction", {}), "materials": materials, "entity_aliases": aliases,
        "interpretation": "Frozen source library, not a gold graph. Search hit is not evidence that a proposed relationship is true."}
    (root / "corpus.json").write_text(json.dumps(corpus, ensure_ascii=False, indent=2) + "\n")
    (root / "source_receipts.json").write_text(json.dumps(receipts, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"corpus_root": str(root), "material_count": len(materials), "corpus_sha256": hashlib.sha256((root / "corpus.json").read_bytes()).hexdigest()}))
