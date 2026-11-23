"""Reviewed perceptual hashes and bounded, metadata-free PNG evidence."""
from io import BytesIO
import hashlib
import warnings

from xti.domain.brand_protection import MAX_ARTIFACT, BrandProtectionError


def fingerprint(data):
    from PIL import Image, ImageOps
    import imagehash
    if not isinstance(data,bytes) or not 0<len(data)<=4*1024*1024: raise BrandProtectionError('invalid_image','Görsel boyutu geçersiz.')
    with warnings.catch_warnings():
        warnings.simplefilter('error',Image.DecompressionBombWarning)
        try:
            with Image.open(BytesIO(data)) as opened:
                if opened.width*opened.height>16_000_000 or min(opened.size)<8:raise ValueError()
                if getattr(opened,'n_frames',1)>1: opened.seek(0)
                source=ImageOps.exif_transpose(opened).convert('RGBA')
                canvas=Image.new('RGB',source.size,'white');canvas.paste(source,mask=source.getchannel('A'))
                canvas.thumbnail((1280,800))
                small=canvas.copy();small.thumbnail((256,256))
                result={'phash':str(imagehash.phash(small)),'dhash':str(imagehash.dhash(small)),
                    'colorhash':str(imagehash.colorhash(small)),'entropy':round(small.convert('L').entropy(),4),
                    'width':canvas.width,'height':canvas.height,'algorithm':'ImageHash-4.3.2/phash8+dhash8+colorhash3'}
                out=BytesIO();canvas.save(out,format='PNG',optimize=True)
                encoded=out.getvalue()
                if len(encoded)>MAX_ARTIFACT:
                    canvas.thumbnail((800,500));out=BytesIO();canvas.save(out,format='PNG',optimize=True);encoded=out.getvalue()
                if len(encoded)>MAX_ARTIFACT:raise ValueError()
                return result,encoded
        except (OSError,ValueError,Image.DecompressionBombError,Image.DecompressionBombWarning):
            raise BrandProtectionError('invalid_image','Görsel güvenli piksel/biçim sınırında çözülemedi.') from None


def artifact(data,role):
    visual,png=fingerprint(data)
    return visual,{'sha256':hashlib.sha256(png).hexdigest(),'bytes':len(png),'role':role},png
