"""Recovered PAK/WIL/WZL asset browser helpers."""
from __future__ import annotations
import threading
from collections import OrderedDict
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from PIL import Image, ImageDraw

THUMB_SIZE=104
CELL_WIDTH=142
CELL_HEIGHT=154
VISIBLE_ROW_PADDING=2
RESAMPLE=Image.Resampling.LANCZOS
APP_VERSION='v63'
IMAGE_DECODE_CACHE_MAX_PIXELS=100663296
IMAGE_DECODE_CACHE_VERSION=3
_THUMBNAIL_MEMORY_CACHE_MAX=2400
_RECOVERED_KINDS=frozenset({'recovered_pak','recovered_wzl','recovered_wil','recovered_wis'})
_IMAGE_DECODE_CACHE=OrderedDict(); _IMAGE_DECODE_CACHE_PIXELS=0; _IMAGE_DECODE_CACHE_LOCK=threading.RLock()
_THUMBNAIL_MEMORY_CACHE=OrderedDict(); _THUMBNAIL_MEMORY_CACHE_LOCK=threading.RLock()

@dataclass
class AssetRecord:
    uid: int; source_index: str; file_name: str; path: Path | None; width: int; height: int; color_format: str; method: str; kind: str
    pak_path: Path | None=None; data_off: int=0; data_len: int=0; raw_len: int=0; raw: bytes | None=None
    bits: int=0; stride: int=0; alpha_stride: int=0; enc1: int=-1; enc2: int=-1; transparent_zero: bool=True
    image: Image.Image | None=None; compressed_size: int=0; origin_x: int=0; origin_y: int=0
    _image_cache: Image.Image | None=None; _cache_kind: str=''; original_uid: int=-1; source_magic: str=''
    @property
    def title(self)-> str:
        size=f'{self.width}x{self.height}' if (self.width and self.height) else 'empty'; return f'{self.source_index}  {size}'
    @property
    def summary(self)-> str:
        parts=[self.color_format,self.method,self.kind]
        return ' / '.join(part for part in parts if part)

def _record_is_recovered(record: AssetRecord)-> bool: return record.kind in _RECOVERED_KINDS

def mark_records_native_authorized(records, authorization_id: str):
    value=str(authorization_id or '').strip().lower()
    if len(value)!=64 or any(ch not in '0123456789abcdef' for ch in value):
        raise ValueError('invalid native asset authorization id')
    for record in records:
        setattr(record,'_native_asset_authorization_id',value)
    return records

def _record_cache_file_signature(path: Path | None)-> tuple[object, ...]:
    if path is None: return (None,)
    try:
        resolved=Path(path).resolve(); st=resolved.stat(); return (str(resolved),st.st_size,st.st_mtime_ns)
    except OSError:
        return (str(path),None,None)

def image_decode_cache_key(record: AssetRecord)-> tuple[object, ...] | None:
    if not _record_is_recovered(record): return None
    return ('recovered',IMAGE_DECODE_CACHE_VERSION,_record_cache_file_signature(record.pak_path),record.uid,record.source_index,record.kind,record.data_off,record.data_len,record.raw_len,record.width,record.height,record.bits,record.stride,record.alpha_stride,record.enc1,record.enc2,record.transparent_zero,record.compressed_size,record.origin_x,record.origin_y,record.source_magic)

def thumbnail_memory_cache_key(record: AssetRecord)-> tuple[object, ...] | None:
    image_key=image_decode_cache_key(record)
    if image_key is None:
        if record.kind in {'empty','blank'}: return ('thumb',THUMB_SIZE,record.kind,record.width,record.height,record.source_index)
        return None
    return ('thumb',THUMB_SIZE,image_key)

def _image_cache_pixels(image: Image.Image)-> int:
    width,height=image.size; return max(1,width)*max(1,height)

def get_decoded_image_cache(record: AssetRecord)-> Image.Image | None:
    key=image_decode_cache_key(record)
    if key is None: return None
    with _IMAGE_DECODE_CACHE_LOCK:
        image=_IMAGE_DECODE_CACHE.get(key)
        if image is None: return None
        _IMAGE_DECODE_CACHE.move_to_end(key); return image.copy()

def put_decoded_image_cache(record: AssetRecord, image: Image.Image)-> None:
    global _IMAGE_DECODE_CACHE_PIXELS
    key=image_decode_cache_key(record)
    if key is None: return
    cached=image.copy(); pixels=_image_cache_pixels(cached)
    with _IMAGE_DECODE_CACHE_LOCK:
        old=_IMAGE_DECODE_CACHE.pop(key,None)
        if old is not None: _IMAGE_DECODE_CACHE_PIXELS-=_image_cache_pixels(old)
        _IMAGE_DECODE_CACHE[key]=cached; _IMAGE_DECODE_CACHE_PIXELS+=pixels
        while _IMAGE_DECODE_CACHE and _IMAGE_DECODE_CACHE_PIXELS>IMAGE_DECODE_CACHE_MAX_PIXELS:
            _old_key,old_image=_IMAGE_DECODE_CACHE.popitem(last=False); _IMAGE_DECODE_CACHE_PIXELS-=_image_cache_pixels(old_image)

def clear_decoded_image_cache()-> None:
    global _IMAGE_DECODE_CACHE_PIXELS
    with _IMAGE_DECODE_CACHE_LOCK: _IMAGE_DECODE_CACHE.clear(); _IMAGE_DECODE_CACHE_PIXELS=0

def get_thumbnail_memory_cache(record: AssetRecord)-> Image.Image | None:
    key=thumbnail_memory_cache_key(record)
    if key is None: return None
    with _THUMBNAIL_MEMORY_CACHE_LOCK:
        image=_THUMBNAIL_MEMORY_CACHE.get(key)
        if image is None: return None
        _THUMBNAIL_MEMORY_CACHE.move_to_end(key); return image.copy()

def put_thumbnail_memory_cache(record: AssetRecord, image: Image.Image)-> None:
    key=thumbnail_memory_cache_key(record)
    if key is None: return
    with _THUMBNAIL_MEMORY_CACHE_LOCK:
        _THUMBNAIL_MEMORY_CACHE[key]=image.copy(); _THUMBNAIL_MEMORY_CACHE.move_to_end(key)
        while len(_THUMBNAIL_MEMORY_CACHE)>_THUMBNAIL_MEMORY_CACHE_MAX: _THUMBNAIL_MEMORY_CACHE.popitem(last=False)

def clear_thumbnail_memory_cache()-> None:
    with _THUMBNAIL_MEMORY_CACHE_LOCK: _THUMBNAIL_MEMORY_CACHE.clear()

_PENDING_METADATA_ATTRS = ('_pending_metadata', '_pending_metadata_corrections', '_metadata_corrections', 'pending_metadata')
_INT_METADATA_FIELDS = frozenset({'width', 'height', 'origin_x', 'origin_y', 'bits', 'stride', 'alpha_stride', 'enc1', 'enc2', 'compressed_size', 'raw_len', 'data_off', 'data_len', 'original_uid'})
_STR_METADATA_FIELDS = frozenset({'file_name', 'color_format', 'method', 'kind', 'source_magic', '_cache_kind'})

def _pending_record_metadata(record: AssetRecord)-> dict[str, object]:
    merged: dict[str, object]={}
    for attr in _PENDING_METADATA_ATTRS:
        value=getattr(record,attr,None)
        if isinstance(value,dict):
            merged.update(value)
    return merged

def _coerced_metadata_value(field: str, value: object)-> object:
    if field in _INT_METADATA_FIELDS: return int(value or 0)
    if field in _STR_METADATA_FIELDS: return str(value or '')
    raise KeyError(field)

def asset_record_has_pending_metadata(_record: AssetRecord)-> bool:
    for field,value in _pending_record_metadata(_record).items():
        try: corrected=_coerced_metadata_value(str(field),value)
        except (KeyError,TypeError,ValueError): continue
        current=getattr(_record,str(field),None)
        if str(field) in _INT_METADATA_FIELDS:
            try: current=int(current or 0)
            except (TypeError,ValueError): current=0
        elif str(field) in _STR_METADATA_FIELDS:
            current=str(current or '')
        if current!=corrected: return True
    return False

def persist_record_corrections(_record: AssetRecord)-> bool:
    changed=False
    for field,value in _pending_record_metadata(_record).items():
        field=str(field)
        try: corrected=_coerced_metadata_value(field,value)
        except (KeyError,TypeError,ValueError): continue
        current=getattr(_record,field,None)
        if field in _INT_METADATA_FIELDS:
            try: current=int(current or 0)
            except (TypeError,ValueError): current=0
        elif field in _STR_METADATA_FIELDS:
            current=str(current or '')
        if current!=corrected:
            setattr(_record,field,corrected)
            changed=True
    if changed:
        for attr in _PENDING_METADATA_ATTRS:
            if hasattr(_record,attr):
                try: setattr(_record,attr,{})
                except Exception: continue
        with suppress(Exception):
            _record._image_cache=None
        clear_decoded_image_cache()
        clear_thumbnail_memory_cache()
    return changed

def read_magic(path: Path)-> str:
    source=Path(path); suffix=source.suffix.lower()
    if suffix in {'.wzl','.wzx'}: return 'WZL'
    if suffix in {'.wil','.wix'}: return 'WIL'
    if suffix=='.wis': return 'WIS'
    with source.open('rb') as handle: data=handle.read(32)
    signatures=((b'SWPAK01\x00','SWPAK'),(b'PACK','GOMPACK'),(b'\x07GEEPAK3','GEEPAK3'),(b'\x07GEEPAK2','GEEPAK2'),(b'\x05GEEM2','GEEM2LP'),(b'\nGAMEOFMIR2','GAMEOFMIR2'),(b'\tGAMEOFMIR','GAMEOFMIR'),(b'GAMEOFMIR2','GAMEOFMIR2'),(b'GAMEOFMIR','GAMEOFMIR'))
    for prefix,magic in signatures:
        if data.startswith(prefix): return magic
    if data.startswith((b'D3DM2',b'MIRYQ',b'GEEM2')): return 'D3DM2'
    length=data[0] if data else 0
    return data[1:1+length].decode('ascii','replace') if 0<length<len(data) else ''

def default_password_for_magic(magic: str)-> str:
    value=str(magic or '').upper()
    if value in {'GOMPACK','GAMEOFMIR2','GAMEOFMIR'}: return 'gameofmir'
    if value=='GEEPAK3': return 'V8M2'
    return ''

def checkerboard(size: tuple[int, int], tile: int=8)-> Image.Image:
    image=Image.new('RGBA',size,(255,255,255,255)); draw=ImageDraw.Draw(image)
    for y in range(0,size[1],tile):
        for x in range(0,size[0],tile):
            fill=(232,236,241,255) if (x//tile+y//tile)%2 else (248,250,252,255); draw.rectangle((x,y,x+tile-1,y+tile-1),fill=fill)
    return image

def _import_record_to_image():
    try: from .recovered_asset_reader import record_to_image
    except ImportError: from core.npc_preview.recovered_asset_reader import record_to_image
    return record_to_image

def image_for_record(record: AssetRecord)-> Image.Image:
    if record.kind=='empty': raise ValueError(f'asset slot {record.source_index} is empty')
    if record.kind=='blank': return Image.new('RGBA',(max(1,record.width),max(1,record.height)),(0,0,0,0))
    if not _record_is_recovered(record): raise ValueError(f'unsupported asset record kind: {record.kind or "<empty>"}')
    authorization_id=str(getattr(record,'_native_asset_authorization_id','') or '').strip().lower()
    if len(authorization_id)!=64 or any(ch not in '0123456789abcdef' for ch in authorization_id):
        raise PermissionError('native NPC asset authorization is required')
    cached=get_decoded_image_cache(record)
    if cached is not None: return cached
    native_worker=getattr(record,'_native_asset_worker',None)
    native_handle=str(getattr(record,'_native_asset_handle','') or '')
    native_index_handle=str(getattr(record,'_native_asset_index_handle','') or '')
    native_generation=int(getattr(record,'_native_worker_generation',0) or 0)
    if native_worker is not None and native_handle:
        width,height,stride,origin_x,origin_y,pixels=native_worker.decode_image(native_handle,native_generation,int(record.uid),native_index_handle or None)
        image=Image.frombytes('RGBA',(width,height),pixels,'raw','BGRA',stride,1)
    else:
        image=record.image.convert('RGBA') if record.image is not None else _import_record_to_image()(record).convert('RGBA')
    image.load(); put_decoded_image_cache(record,image); return image.copy()

def _draw_status_tile(label: str, fill: tuple[int, int, int, int])-> Image.Image:
    tile=checkerboard((THUMB_SIZE,THUMB_SIZE),8); draw=ImageDraw.Draw(tile); draw.rectangle((18,18,THUMB_SIZE-18,THUMB_SIZE-18),outline=(176,184,192,255),width=1); draw.text((THUMB_SIZE//2,THUMB_SIZE//2),label,anchor='mm',fill=fill); return tile

def thumbnail_for(record: AssetRecord)-> Image.Image:
    cached=get_thumbnail_memory_cache(record)
    if cached is not None: return cached
    if record.kind=='empty':
        thumb=_draw_status_tile('EMPTY',(135,142,150,255)); put_thumbnail_memory_cache(record,thumb); return thumb
    if record.kind=='blank':
        thumb=_draw_status_tile('BLANK',(120,128,136,255)); put_thumbnail_memory_cache(record,thumb); return thumb
    image=image_for_record(record); image.thumbnail((THUMB_SIZE,THUMB_SIZE),RESAMPLE); min_visible=max(28,THUMB_SIZE//3)
    if image.width and image.height and min(image.width,image.height)<min_visible:
        scale=min(THUMB_SIZE/image.width,THUMB_SIZE/image.height,min_visible/min(image.width,image.height)); image=image.resize((max(1,int(image.width*scale)),max(1,int(image.height*scale))),RESAMPLE)
    tile=checkerboard((THUMB_SIZE,THUMB_SIZE),8); x=(THUMB_SIZE-image.width)//2; y=(THUMB_SIZE-image.height)//2; tile.alpha_composite(image,(x,y)); put_thumbnail_memory_cache(record,tile); return tile

__all__ = [
    'APP_VERSION',
    'AssetRecord',
    'asset_record_has_pending_metadata',
    'checkerboard',
    'clear_decoded_image_cache',
    'clear_thumbnail_memory_cache',
    'default_password_for_magic',
    'get_decoded_image_cache',
    'get_thumbnail_memory_cache',
    'image_for_record',
    'mark_records_native_authorized',
    'persist_record_corrections',
    'put_decoded_image_cache',
    'put_thumbnail_memory_cache',
    'read_magic',
    'thumbnail_for',
]
