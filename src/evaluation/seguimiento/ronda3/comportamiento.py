"""Señales sin etiquetas, calculadas con operaciones de minutos anteriores.

El historial pertenece exclusivamente a la muestra de desarrollo autorizada.
Los eventos simultáneos no se usan como antecedentes entre sí.
"""
import numpy as np
import pandas as pd

FEATURES = [
    'card_prior_count_log','card_prior_mean_abs_amount','card_prior_std_abs_amount',
    'amount_over_card_prior_mean','amount_card_zscore','card_hours_since_previous_log',
    'card_previous_24h_count_log','card_previous_7d_count_log','card_prior_online_share',
    'card_new_merchant','card_new_city','user_prior_count_log','user_prior_mean_abs_amount',
    'amount_over_user_prior_mean','merchant_prior_count_log','amount_over_merchant_prior_mean',
]


def aggregates(frame, entity, rolling=False):
    work = frame[[entity,'transaction_date','abs_amount','online']].copy()
    work['squared'] = work.abs_amount ** 2
    blocks = work.groupby([entity,'transaction_date'],sort=True).agg(
        count=('abs_amount','size'),total=('abs_amount','sum'),
        square=('squared','sum'),online_count=('online','sum')).reset_index()
    names = ['count','total','square','online_count']
    cumulative = blocks.groupby(entity,sort=False)[names].cumsum() - blocks[names]
    n = cumulative['count']
    mean = cumulative.total / n.replace(0,np.nan)
    variance = (cumulative.square / n.replace(0,np.nan) - mean**2).clip(lower=0)
    blocks['n_prior'] = n
    blocks['mean_prior'] = mean
    blocks['std_prior'] = np.sqrt(variance)
    blocks['online_prior'] = cumulative.online_count / n.replace(0,np.nan)
    blocks['hours_previous'] = blocks.groupby(entity).transaction_date.diff().dt.total_seconds()/3600
    outnames = ['n_prior','mean_prior','std_prior','online_prior','hours_previous']
    if rolling:
        for days in [1,7]:
            name = f'count_{days}d'
            counts = np.zeros(len(blocks),dtype=np.int64)
            for idx in blocks.groupby(entity,sort=False).indices.values():
                times = blocks.iloc[idx].transaction_date.astype('int64').to_numpy()
                left = np.searchsorted(times,times-pd.Timedelta(days=days).value,side='left')
                prefix = np.r_[0,np.cumsum(blocks.iloc[idx]['count'].to_numpy(),dtype=np.int64)]
                counts[idx] = prefix[:-1]-prefix[left]
            blocks[name] = counts
            outnames.append(name)
    result = frame[['transaction_id',entity,'transaction_date']].merge(
        blocks[[entity,'transaction_date']+outnames],on=[entity,'transaction_date'],
        how='left',validate='many_to_one').set_index('transaction_id')
    return result[outnames].reindex(frame.transaction_id)


def build_features(data):
    # La selección explícita impide que etiquetas o atributos de fotografía
    # de usuarios/tarjetas entren en los agregados históricos.
    cols = ['transaction_id','transaction_date','amount','use_chip',
            'source_card_id','source_client_id','source_merchant_id','source_merchant_city']
    f = data[cols].copy()
    if f.transaction_id.isna().any() or not f.transaction_id.is_unique:
        raise ValueError('Identificadores repetidos o ausentes.')
    f['transaction_date'] = pd.to_datetime(f.transaction_date,errors='raise')
    if f.transaction_date.isna().any():raise ValueError('Fecha ausente.')
    f['abs_amount'] = pd.to_numeric(f.amount,errors='raise').abs()
    if not np.isfinite(f.abs_amount).all():raise ValueError('Importe no finito.')
    for c in ['source_card_id','source_client_id','source_merchant_id']:
        if f[c].isna().any():raise ValueError('Falta clave de contexto: '+c)
        f[c] = f[c].astype(str)
    f['online'] = (f.use_chip=='Online Transaction').astype(int)
    f = f.sort_values(['transaction_date','transaction_id']).reset_index(drop=True)
    amount = f.set_index('transaction_id').abs_amount
    result = pd.DataFrame(index=pd.Index(f.transaction_id,name='transaction_id'))
    card = aggregates(f,'source_card_id',rolling=True)
    result['card_prior_count_log'] = np.log1p(card.n_prior)
    result['card_prior_mean_abs_amount'] = card.mean_prior
    result['card_prior_std_abs_amount'] = card.std_prior
    result['amount_over_card_prior_mean'] = amount/card.mean_prior.clip(lower=1)
    result['amount_card_zscore'] = (amount-card.mean_prior)/card.std_prior.clip(lower=1)
    result['card_hours_since_previous_log'] = np.log1p(card.hours_previous)
    result['card_previous_24h_count_log'] = np.log1p(card.count_1d)
    result['card_previous_7d_count_log'] = np.log1p(card.count_7d)
    result['card_prior_online_share'] = card.online_prior
    for entity, output in [('source_merchant_id','card_new_merchant'),('source_merchant_city','card_new_city')]:
        first = f.groupby(['source_card_id',entity],dropna=False).transaction_date.transform('min')
        value = (first == f.transaction_date).astype(float)
        if entity=='source_merchant_city':value = value.mask(f[entity].isna()|f[entity].eq(''))
        result[output] = value.to_numpy()
    user = aggregates(f,'source_client_id')
    result['user_prior_count_log'] = np.log1p(user.n_prior)
    result['user_prior_mean_abs_amount'] = user.mean_prior
    result['amount_over_user_prior_mean'] = amount/user.mean_prior.clip(lower=1)
    merchant = aggregates(f,'source_merchant_id')
    result['merchant_prior_count_log'] = np.log1p(merchant.n_prior)
    result['amount_over_merchant_prior_mean'] = amount/merchant.mean_prior.clip(lower=1)
    if np.isinf(result.to_numpy()).any():raise ValueError('Señal infinita.')
    return result[FEATURES].reindex(data.transaction_id)
