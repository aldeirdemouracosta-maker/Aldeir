import pytest

from frameltx.config import APP_DIR
from frameltx.workflows import (
    WORKFLOW_FILES, WorkflowError, build_workflow, find_placeholders, load_template, missing_node_types,
)

WF_DIR = APP_DIR / "workflows"


def full_params(template):
    return {name: f"v_{name}" for name in find_placeholders(template)} | {"seed": 42, "width": 480}


@pytest.mark.parametrize("name", list(WORKFLOW_FILES))
def test_templates_load_and_fill(name):
    template = load_template(WF_DIR, name)
    wf = build_workflow(template, full_params(template))
    assert not find_placeholders(wf), "nenhum placeholder deve sobrar"
    for node in wf.values():
        assert "_optional" not in node
        for value in node["inputs"].values():
            if isinstance(value, list) and len(value) == 2 and isinstance(value[1], int):
                assert value[0] in wf, f"ligação quebrada para o nó {value[0]}"


def test_typed_substitution_keeps_int():
    template = load_template(WF_DIR, "ltx_t2v")
    wf = build_workflow(template, full_params(template))
    assert wf["10"]["inputs"]["noise_seed"] == 42
    assert wf["6"]["inputs"]["width"] == 480


def test_framepack_end_image_is_optional():
    template = load_template(WF_DIR, "framepack")
    params = full_params(template) | {"end_image": None}
    wf = build_workflow(template, params)
    assert not {"20", "21", "22", "23"} & wf.keys()
    sampler = wf["30"]["inputs"]
    assert "end_latent" not in sampler and "end_image_embeds" not in sampler
    assert sampler["start_latent"] == ["12", 0]


def test_missing_placeholder_raises():
    template = load_template(WF_DIR, "ltx_t2v")
    with pytest.raises(WorkflowError, match="Faltam valores"):
        build_workflow(template, {"prompt": "x"})


def test_missing_node_types():
    template = load_template(WF_DIR, "ltx_t2v")
    assert "LTXVConcatAVLatent" in missing_node_types(template, {"CLIPTextEncode": {}})


def test_non_api_format_rejected(tmp_path):
    (tmp_path / "bad.json").write_text('{"nodes": [], "links": []}')
    with pytest.raises(WorkflowError, match="formato API"):
        load_template(tmp_path, "bad")
