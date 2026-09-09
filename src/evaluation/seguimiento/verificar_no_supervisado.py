"""Comprueba métricas, selección y persistencia desde un ensayo Isolation Forest terminado."""
import argparse
import hashlib
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import confusion_matrix, average_precision_score, roc_auc_score
from no_supervisado import normalize, NUMERIC, CATEGORICAL, write_json


def verify(data_path, experiment, rf):
    metrics = pd.read_csv(experiment / 'comparacion.csv', float_precision='round_trip')
    models = pd.read_csv(experiment / 'modelos_y_tiempos.csv')
    info = json.loads(Path(str(data_path) + '.json').read_text())
    assert info['test_excluded'] is True
    assert info['excluded_test_ids_sha256'] == '3ef703a97097fe3f62d68220d894c2d89cd5a2f9bcfe8104e3cfe0259dfb4a08'
    assert hashlib.sha256(data_path.read_bytes()).hexdigest() == info['file_sha256']
    data = normalize(pd.read_csv(data_path)).set_index('transaction_id')
    assert len(data) == 841721 and data.index.is_unique and data.is_fraud.sum() == 1201
    assert len(metrics) == 12 and len(models) == 3
    for _, row in metrics.iterrows():
        year = int(row.evaluation_year)
        base = experiment if row.candidate == 'isolation_forest' else rf
        ev = pd.read_csv(base / f'predicciones_{year}_{row.candidate}_evaluation.csv.gz', float_precision='round_trip')
        va = pd.read_csv(base / f'predicciones_{year}_{row.candidate}_validation.csv.gz', float_precision='round_trip')
        assert ev.transaction_id.is_unique and va.transaction_id.is_unique
        assert not set(ev.transaction_id) & set(va.transaction_id)
        for frame in [va, ev]:
            assert np.array_equal(data.loc[frame.transaction_id].is_fraud, frame.is_fraud)
        assert set(ev.transaction_id) == set(data[data.transaction_date.dt.year == year].index)
        tn, fp, fn, tp = confusion_matrix(ev.is_fraud, ev.score >= row.threshold, labels=[0, 1]).ravel()
        expected = dict(tn=tn, fp=fp, fn=fn, tp=tp, recall=tp/(tp+fn),
                        precision=tp/(tp+fp) if tp+fp else 0., f1=2*tp/(2*tp+fp+fn),
                        cost=3*(tp+fp)+row.fn_cost*fn,
                        average_precision=average_precision_score(ev.is_fraud, ev.score),
                        roc_auc=roc_auc_score(ev.is_fraud, ev.score))
        for key, value in expected.items():
            assert np.isclose(row[key], value, rtol=1e-12, atol=1e-12), (year, key)
        # Recalculate complete tie groups independently from threshold_curve.
        groups = va.groupby('score').is_fraud.agg(['count', 'sum']).sort_index(ascending=False)
        tps = np.r_[0, groups['sum'].cumsum().to_numpy()]
        alerts = np.r_[0, groups['count'].cumsum().to_numpy()]
        fps, fns = alerts-tps, int(va.is_fraud.sum())-tps
        thresholds = np.r_[np.nextafter(1., 2.), groups.index.to_numpy()]
        costs = 3*alerts+row.fn_cost*fns
        if row.policy == 'costo_capacidad_50':
            eligible = np.flatnonzero(alerts/len(va)*10000 <= 50)
            best = eligible[np.argmin(costs[eligible])]
        else:
            best = int(np.argmax(2*tps/(2*tps+fps+fns)))
        assert thresholds[best] == row.threshold
        assert np.isclose(costs[best], row.validation_cost, rtol=1e-12)
    for year in [2015, 2016, 2019]:
        path = experiment / f'isolation_forest_{year}.joblib'
        expected_hash = models.loc[models.evaluation_year == year, 'model_sha256'].iloc[0]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected_hash
        predicted = pd.read_csv(experiment / f'predicciones_{year}_isolation_forest_evaluation.csv.gz', float_precision='round_trip').iloc[:256]
        inp = data.loc[predicted.transaction_id, NUMERIC+CATEGORICAL]
        model = joblib.load(path)
        assert np.allclose(-model.score_samples(inp), predicted.score, rtol=0, atol=1e-12)
    result = {'status':'passed', 'comparison_rows_recomputed':12, 'validation_choices_verified':12,
              'saved_models_sha256_verified':3, 'reloaded_predictions_per_model':256,
              'absolute_tolerance':1e-12, 'new_fits':0, 's9_test_reopened':False}
    write_json(experiment / 'verificacion.json', result)
    print(json.dumps(result))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, required=True)
    parser.add_argument('--experiment', type=Path, required=True)
    parser.add_argument('--rf-predictions', type=Path, required=True)
    args = parser.parse_args()
    verify(args.data, args.experiment, args.rf_predictions)
