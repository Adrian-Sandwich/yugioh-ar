"""Title OCR: real photograph, five rendered languages, ambiguity and independent evidence."""
import json,sqlite3,tempfile,time
from pathlib import Path
import cv2,numpy as np
from PIL import Image,ImageDraw,ImageFont
from name_ocr import NameRegistry,mark_conflicts
from passcode_ocr import ROOT,SIZE,NumberReader,rectify,GeometryRefiner,lookup


def observation(text,score=.96,orientation=0):
    return {'text':text,'score':score,'orientation':orientation,'variant':'test'}


def main():
    out=ROOT/'research/qa/name-ocr';out.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=ROOT/'.runtime') as temporary:
        path=Path(temporary)/'names.sqlite'
        db=sqlite3.connect(path);db.execute('CREATE TABLE names(card_id TEXT,language TEXT,name TEXT)')
        db.executemany('INSERT INTO names VALUES (?,?,?)',[
            ('blue','en','Blue-Eyes White Dragon'),('blue','es','Dragón Blanco de Ojos Azules'),
            ('dark','en','Dark Magician'),('one','en','Shared Name'),('two','fr','Shared Name')]);db.commit()
        index=NameRegistry(path,refresh_seconds=0)
        assert index.resolve([observation('BLUE—EYES WHITE DRAGON')])['status']=='matched'
        ambiguous=index.resolve([observation('Shared Name')]);assert ambiguous['status']=='ambiguous' and len(ambiguous['matches'])==2
        assert index.resolve([observation('Blue-Eyes White Dragon'),observation('Dark Magician',orientation=180)])['status']=='ambiguous'
        typo=index.resolve([observation('BLUE-EYES WH1TE DRAGON')])
        assert typo['status']=='not_in_registry' and not typo['matches'] and typo['suggestions']
        assert index.resolve([observation('Blue-Eyes White Dragon',.70)])['status']=='low_confidence'
        accent=index.resolve([observation('Dragon Blanco de Ojos Azules')])
        assert not accent['matches'] and accent['suggestions'],'Accent folding silently confirmed identity'
        exact=index.resolve([observation('Blue-Eyes White Dragon')])
        assert mark_conflicts(exact,'dark',[],False)['visual_conflict']
        exact=index.resolve([observation('Blue-Eyes White Dragon')])
        assert mark_conflicts(exact,None,[{'card_id':'dark'}],True)['serial_conflict']
        exact=index.resolve([observation('Blue-Eyes White Dragon')])
        assert not mark_conflicts(exact,None,[{'card_id':'dark'}],False)['serial_conflict']
        db.execute("INSERT INTO names VALUES ('new','pt','Nova Carta')");db.commit()
        assert index.resolve([observation('Nova Carta')])['status']=='matched','Index failed to refresh after write'
        db.close()
    reader=NumberReader()
    blank=np.full((SIZE[1],SIZE[0],3),200,np.uint8)
    assert reader.read_name(blank)['status']=='unreadable'
    ref=json.loads((ROOT/'data/references/catalog.json').read_text(encoding='utf-8'))[0]
    image=cv2.imread(str((ROOT/'data/references'/ref['source']).resolve()))
    corners=GeometryRefiner(image).refine(ref['corners'])['corners'];card,_,_=rectify(image,corners)
    start=time.monotonic();title=reader.read_name(card);elapsed=(time.monotonic()-start)*1000
    uid=lookup('89631139')[0]['card_id']
    assert title['status']=='matched' and title['matches'][0]['card_id']==uid,title
    turned=reader.read_name(np.ascontiguousarray(np.rot90(card,2)))
    assert turned['status']=='matched' and turned['orientation']==180,turned
    db=sqlite3.connect((ROOT/'data/registry/registry.sqlite').as_uri()+'?mode=ro',uri=True)
    languages=[]
    try:
        for language in ('en','es','de','fr','pt'):
            name=db.execute("SELECT name FROM names WHERE card_id=? AND language=? ORDER BY CASE WHEN source LIKE 'neuron:%' THEN 0 ELSE 1 END LIMIT 1",(uid,language)).fetchone()[0]
            im=Image.new('RGB',SIZE,(205,190,150));draw=ImageDraw.Draw(im)
            font=ImageFont.truetype('C:/Windows/Fonts/timesbd.ttf',32)
            while draw.textlength(name.upper(),font=font)>500:font=ImageFont.truetype('C:/Windows/Fonts/timesbd.ttf',font.size-1)
            draw.text((30,38),name.upper(),fill=(25,25,25),font=font)
            fixture=cv2.cvtColor(np.array(im),cv2.COLOR_RGB2BGR)
            result=reader.read_name(fixture)
            cv2.imwrite(str(out/f'rendered-{language}.png'),fixture)
            assert result['status']=='matched' and uid in {m['card_id'] for m in result['matches']},(language,name,result)
            languages.append({'language':language,'expected':name,'reading':result['text'],'score':result['score'],'fixture':'rendered text, not a physical card'})
    finally:db.close()
    result={'status':'passed','real_photo':title,'real_photo_name_ms_single_run':round(elapsed,1),
        'rendered_language_checks':languages,'checks':['exact normalized names','punctuation','ambiguity across identities/orientations',
        'typos are suggestions only','low score rejected','diacritics not silently removed','visual/serial conflicts','index refresh','blank rejection','180-degree orientation']}
    (out/'validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
