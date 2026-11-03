"""Visualizzazione su richiesta di un PDF citato, per la demo universitaria.

L'archivio regionale contiene i PDF originali ma il link allo ZIP non
permette di aprirli alla pagina giusta: estraiamo SOLO il PDF richiesto,
se disponibile. Non altera il DB o i motori TAG/Text-to-SQL.
"""
from __future__ import annotations

from io import BytesIO
from pathlib import PurePosixPath
from urllib.parse import unquote, urlsplit
from urllib.request import urlopen
from zipfile import BadZipFile, ZipFile

MAX_ARCHIVE_BYTES = 95_000_000
MAX_PDF_BYTES = 18_000_000


def _validated_regional_archive(url):
    parsed=urlsplit(url)
    if (parsed.scheme!="https"
        or parsed.hostname!="www.regione.campania.it"
        or parsed.username is not None or parsed.password is not None
        or not unquote(parsed.path).lower().endswith(".zip")):
        raise ValueError("Archivio ufficiale regionale non riconosciuto")
    return url


def extract_cited_pdf(blob, path):
    """Restituisce byte PDF dal file ZIP, mai da un nome ambiguo."""
    expected=path.replace("\\","/").strip("/").casefold()
    if not expected or ".." in PurePosixPath(expected).parts:
        raise ValueError("Nome PDF non valido")
    with ZipFile(BytesIO(blob)) as archive:
        files=[x for x in archive.infolist()
               if not x.is_dir() and x.filename.casefold().endswith(".pdf")]
        exact=[x for x in files
               if x.filename.replace("\\","/").strip("/").casefold()==expected]
        if len(exact)==1:
            selected=exact[0]
        elif len(exact)>1:
            raise ValueError("Documento PDF ambiguo")
        else:
            # Alcuni ZIP non includono la stessa cartella del percorso nel DB.
            base=PurePosixPath(expected).name
            same=[x for x in files
                  if PurePosixPath(x.filename.replace("\\","/").casefold()).name==base]
            if len(same)!=1:
                raise ValueError("PDF non individuato univocamente nell'archivio")
            selected=same[0]
        if selected.file_size>MAX_PDF_BYTES:
            raise ValueError("PDF troppo grande per l'anteprima")
        with archive.open(selected) as handle:
            data=handle.read(MAX_PDF_BYTES+1)
        if len(data)>MAX_PDF_BYTES or not data.startswith(b"%PDF-"):
            raise ValueError("Documento non disponibile come PDF")
        return data


def pdf_from_official_archive(url, path):
    """Scarica lo ZIP ufficiale soltanto quando si apre la fonte."""
    _validated_regional_archive(url)
    with urlopen(url,timeout=18) as source:
        blob=source.read(MAX_ARCHIVE_BYTES+1)
    if len(blob)>MAX_ARCHIVE_BYTES:
        raise ValueError("Archivio troppo grande per la demo")
    try:
        return extract_cited_pdf(blob,path)
    except BadZipFile as exc:
        raise ValueError("Archivio regionale non leggibile") from exc
