"""A real HTTP-level sequence covering the implemented first-release workflow."""
from io import BytesIO

from PIL import Image

SCRIPT = "雨夜公交站，女孩坐在长椅上，看到远处的男人。男人手里握着黑伞，伞柄接触右手。"


def make_image() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (100, 100), "navy").save(buffer, format="PNG")
    return buffer.getvalue()


def test_script_asset_reference_storyboard_and_prompts(client):
    http, llm = client
    project = http.post("/api/projects", json={"title": "雨夜", "style_guide": "写实电影"}).json()
    pid = project["id"]
    script = http.post(f"/api/projects/{pid}/scripts", json={"text": SCRIPT}).json()
    sid = script["id"]
    result = http.post(f"/api/scripts/{sid}/extract", json={}).json()
    assert result["run"]["beat_count"] == 1
    assert len(result["candidates"]) == 4
    invalid = next(c for c in result["candidates"] if c["status"] == "invalid_evidence")
    assert http.post(f"/api/candidates/{invalid['id']}/approve", json={}).status_code == 422
    assert llm.calls.count("script_extract") == 1
    repeated = http.post(f"/api/scripts/{sid}/extract", json={}).json()
    assert repeated["run"]["id"] == result["run"]["id"]
    assert llm.calls.count("script_extract") == 1

    assets=[]
    for candidate in result["candidates"]:
        if candidate["status"] != "pending":
            continue
        response=http.post(f"/api/candidates/{candidate['id']}/approve", json={})
        assert response.status_code == 200, response.text
        assets.append(response.json())
    assert len(assets) == 3
    scene=next(a for a in assets if a["kind"]=="scene")
    response=http.patch(f"/api/assets/{scene['id']}", json={"revision":scene["revision"],"locked_fields":{"screen_side":"right"}})
    assert response.status_code == 200
    assert http.patch(f"/api/assets/{scene['id']}", json={"revision":1,"description":"stale"}).status_code == 409

    polished=http.post(f"/api/assets/{scene['id']}/image-prompts",json={"request":"电影实景参考图"})
    assert polished.status_code == 200, polished.text
    assert "[锁定] screen_side = right" in polished.json()["compiled_prompt"]
    assert polished.json()["approved"] is False
    assert http.post(f"/api/prompts/{polished.json()['id']}/review",json={"approved":True}).status_code==200

    # Reference image is not used before approval; after approval it receives a per-shot slot.
    girl=next(a for a in assets if a["kind"]=="character")
    image=http.post(f"/api/assets/{girl['id']}/references?role=identity",files={"file":("girl.png",make_image(),"image/png")})
    assert image.status_code==201, image.text
    ref=image.json()
    assert ref["approved"] is False
    assert ref["path"] is None
    assert http.get(f"/api/references/{ref['id']}/file").status_code==200
    assert http.post(f"/api/references/{ref['id']}/review",json={"approved":True}).status_code==200

    planned=http.post(f"/api/scripts/{sid}/storyboard",json={"count_limit":12})
    assert planned.status_code==200,planned.text
    shot=planned.json()[0]
    assert girl["id"] in shot["asset_ids"]
    manifest=http.get(f"/api/shots/{shot['id']}/reference-manifest").json()
    assert len(manifest)==1
    assert manifest[0]["slot"]==1 and manifest[0]["asset_name"]=="女孩"
    validation=http.get(f"/api/shots/{shot['id']}/validate").json()
    assert validation["has_errors"] is False

    shot_prompt=http.post(f"/api/shots/{shot['id']}/prompts",json={"purpose":"shot_video","user_guidance":"雨夜悬疑"})
    assert shot_prompt.status_code==200,shot_prompt.text
    text=shot_prompt.json()["compiled_prompt"]
    assert "<Picture 1>" in text and "right" in text and "grips" in text and "0.10" in text
    assert "[资产锁定] screen_side=right" in text
    assert shot_prompt.json()["version"]==1
    updated = http.patch(f"/api/shots/{shot['id']}", json={
        "revision":shot["revision"],"constraints":[
            {"type":"screen_side","subject":"公交站","relation":"screen_side","value":"left","locked":True},
            {"type":"screen_side","subject":"公交站","relation":"screen_side","value":"right","locked":True},
        ]})
    assert updated.status_code==200
    invalid_validation=http.get(f"/api/shots/{shot['id']}/validate").json()
    assert invalid_validation["has_errors"] is True
    assert http.post(f"/api/shots/{shot['id']}/prompts",json={"purpose":"shot_video"}).status_code==422
    assert http.get(f"/api/projects/{pid}/assets").status_code==200


def test_invalid_image_and_cross_project_rejection(client):
    http,_=client
    first=http.post('/api/projects',json={'title':'A'}).json()['id']
    second=http.post('/api/projects',json={'title':'B'}).json()['id']
    asset=http.post(f'/api/projects/{first}/assets',json={'name':'男人','kind':'character'}).json()
    result=http.post(f"/api/assets/{asset['id']}/references?role=identity",files={'file':('bad.png',b'not-an-image','image/png')})
    assert result.status_code==415
    script=http.post(f'/api/projects/{second}/scripts',json={'text':SCRIPT}).json()
    result=http.post(f'/api/projects/{second}/shots',json={'script_id':script['id'],'ordinal':1,'narrative':'人从远处走来','asset_ids':[asset['id']]})
    assert result.status_code==422


def test_health_and_ui_respond(client):
    http,_=client
    assert http.get('/api/health').status_code==200
    assert 'AI短剧智能导演台' in http.get('/').text
    assert 'async function api' in http.get('/app.js').text
