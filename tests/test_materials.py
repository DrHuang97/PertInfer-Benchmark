"""Original-material packaging checks; no agent retrieval dependency."""
import hashlib
import json
import pytest
from pertinfer_benchmark import materials as builder

def source(path, fmt="xml", mid="article"):
    return {"material_id": mid, "title": "Original source", "path": str(path),
            "source_url": "https://example.org/original", "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "format": fmt, "mime_type": "application/" + fmt}


def test_build_keeps_original_bytes_sections_and_source_caption(tmp_path):
    article = tmp_path / "source.xml"
    article.write_text('<article><body><sec id="S1"><title>Results</title><p>Alpha did not bind Beta.</p><fig id="Fig1"><label>Fig. 1</label><caption>Original negative result.</caption></fig></sec></body></article>')
    picture = tmp_path / "figure.jpg"; picture.write_bytes(b"fixture-image-bytes")
    image = source(picture, "image", "figure"); image["caption_from"] = {"material_id": "article", "section": "Fig1"}
    output = tmp_path / "corpus"
    builder.build({"corpus_id": "test", "task_id": "t", "sources": [source(article), image]}, output)
    corpus = json.loads((output / "corpus.json").read_text())
    assert "did not bind" in corpus["materials"][0]["text"]
    assert corpus["materials"][1]["text"] == "Fig. 1 Original negative result."
    artifact = corpus["materials"][0]["artifacts"][0]
    assert (output / artifact["path"]).read_bytes() == article.read_bytes()
    with pytest.raises(FileExistsError):
        builder.build({"sources": []}, output)


def test_source_hash_mismatch_refuses_to_seal(tmp_path):
    path = tmp_path / "source.json"; path.write_text('{"results": []}')
    row = source(path, "json"); path.write_text('{"results": ["modified"]}')
    with pytest.raises(ValueError, match="mismatched"):
        builder.build({"corpus_id": "test", "task_id": "t", "sources": [row]}, tmp_path / "corpus")
    assert not (tmp_path / "corpus/corpus.json").exists()


def test_aliases_come_from_original_entity_records(tmp_path):
    path = tmp_path / "molecules.json"
    path.write_text(json.dumps({"molecules": [{"molecule_chembl_id": "CHEMBL1", "pref_name": "Exact drug", "molecule_synonyms": [{"molecule_synonym": "Alias"}]}]}))
    _, _, aliases = builder.extract(path, "json")
    assert set(aliases[0]) == {"CHEMBL1", "Exact drug", "Alias"}


def test_partial_pdf_not_accepted_as_material(tmp_path):
    path = tmp_path / "partial.pdf"; path.write_bytes(b"%PDF-1.4\ntruncated")
    with pytest.raises(ValueError, match="integrity"):
        builder.extract(path, "pdf")


def test_ensembl_gene_identifiers_are_bridged_from_uniprot_not_hardcoded(tmp_path):
    path = tmp_path / "uniprot.json"
    path.write_text(json.dumps({"results": [{"primaryAccession": "QTEST1", "genes": [{"geneName": {"value": "EXAMPLE"}}],
        "uniProtKBCrossReferences": [{"database": "Ensembl", "id": "ENST00001.3", "properties": [{"key": "GeneId", "value": "ENSG00001.7"}]}]}]}))
    _, _, aliases = builder.extract(path, "json")
    assert {"EXAMPLE", "ENSG00001.7", "ENSG00001", "Ensembl:ENSG00001"} <= set(aliases[0])
    assert "ENST00001.3" not in aliases[0]
