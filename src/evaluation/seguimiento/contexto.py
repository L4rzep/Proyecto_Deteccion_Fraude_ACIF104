"""Extrae cuatro campos transaccionales para los IDs de desarrollo; no lee etiquetas nuevas."""
import argparse
import hashlib
import gzip
import json
from pathlib import Path
import pandas as pd


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(4*1024*1024), b''): h.update(block)
    return h.hexdigest()


def run(args):
    manifest = json.loads(Path(str(args.data)+'.json').read_text())
    if sha(args.data) != manifest['file_sha256'] or manifest['test_excluded'] is not True:
        raise ValueError('Desarrollo sin identidad verificada')
    if manifest['excluded_test_ids_sha256'] != '3ef703a97097fe3f62d68220d894c2d89cd5a2f9bcfe8104e3cfe0259dfb4a08':
        raise ValueError('La exclusión de test no coincide con S9')
    if args.output.exists() or Path(str(args.output)+'.json').exists():
        raise FileExistsError('Seleccione una salida nueva')
    ids = pd.read_csv(args.data, usecols=['transaction_id']).transaction_id
    if len(ids) != 841721 or not ids.is_unique:
        raise ValueError('Desarrollo incompleto o duplicado')
    mapping = {'id':'transaction_id', 'client_id':'source_client_id', 'card_id':'source_card_id',
               'merchant_id':'source_merchant_id', 'merchant_city':'source_merchant_city'}
    parts = []
    for block in pd.read_csv(args.transactions, usecols=list(mapping), chunksize=200000,
                             dtype={k:'string' for k in mapping if k != 'id'}):
        parts.append(block[block.id.isin(ids)].rename(columns=mapping))
    result = pd.concat(parts, ignore_index=True).set_index('transaction_id')
    if not result.index.is_unique or set(result.index) != set(ids):
        raise ValueError('IDs faltantes o repetidos en transactions_data.csv')
    result = result.loc[ids].reset_index()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    payload = result.to_csv(index=False).encode('utf-8')
    if str(args.output).endswith('.gz'):
        payload = gzip.compress(payload, compresslevel=6, mtime=0)
        gzip.decompress(payload)
    temporary = args.output.with_name(args.output.name+'.partial')
    temporary.write_bytes(payload)
    temporary.replace(args.output)
    Path(str(args.output)+'.json').write_text(json.dumps({'file_sha256':sha(args.output),
        'development_sha256':manifest['file_sha256'], 'rows':len(result),
        'raw_transaction_sha256':sha(args.transactions), 'source_columns':mapping,
        'test_excluded':True, 'labels_read_from_original_source':False}, indent=2)+'\n')


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data',type=Path,required=True)
    p.add_argument('--transactions',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    run(p.parse_args())
