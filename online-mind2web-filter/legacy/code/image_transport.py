"""Reuse the already-authorized exact-byte image dedup transport; no sampling or resizing."""
import hashlib,json
from pathlib import Path
from judge_refusals_dedup import deduplicate_exact_images


def transport_gpt_images(kwargs,destination):
    total=sum(part.get('type')=='image_url' for message in kwargs.get('messages',[])
              if isinstance(message.get('content'),list) for part in message['content'])
    if total<=50:
        return
    manifests=deduplicate_exact_images(kwargs)
    actual=sum(m['actual_distinct_image_blocks'] for m in manifests)
    assert actual<=50,'Cannot preserve all distinct screenshots within this gateway image cap; leave judgement unknown'
    text=json.dumps(manifests,sort_keys=True,ensure_ascii=False)
    path=Path(destination)/'image_transport'/(hashlib.sha256(text.encode()).hexdigest()+'.json')
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():
        assert json.loads(path.read_text())==manifests
    else:
        path.write_text(json.dumps(manifests,indent=2)+'\n')
