-- =========================================================================
-- Vista maestra usada por los scripts de entrenamiento
-- (src/analisis_fraude-Full Python.py, src/fase4_xgboost.py)
--
-- Cruza transactions_data + fraud_labels + cards_data + users_data + mcc_codes
-- en un único dataset listo para feature engineering.
--
-- IMPORTANTE: usa INNER JOIN contra fraud_labels, cards_data y users_data.
-- Cualquier transacción sin etiqueta de fraude, sin tarjeta o sin usuario
-- coincidente queda excluida silenciosamente del resultado. Esto es
-- intencional para entrenamiento (no se puede entrenar sin etiqueta), pero
-- explica por qué el conteo de esta vista es menor al de transactions_data
-- completa.
--
-- Verificado contra FraudeDB el 2026-08 (esquema real, no el asumido por
-- versiones antiguas del código: transactions_data.id, no transaction_id;
-- transactions_data.date, no transaction_date; mcc_codes.description, no
-- mcc_description -- esta vista ya resuelve ese renombre en la proyección
-- final con "m.description AS mcc_description").
-- =========================================================================

CREATE VIEW dbo.vw_dataset_maestro
AS
SELECT
    t.id AS transaction_id,
    t.[date] AS transaction_date,
    t.client_id,
    t.card_id,
    TRY_CONVERT(decimal(18,2), REPLACE(t.amount, '$', '')) AS amount,
    t.use_chip,
    t.merchant_id,
    t.merchant_city,
    t.merchant_state,
    t.zip,
    t.mcc,
    t.errors,
    f.is_fraud,
    u.current_age,
    u.retirement_age,
    u.birth_year,
    u.birth_month,
    u.gender,
    u.address,
    u.latitude,
    u.longitude,
    TRY_CONVERT(decimal(18,2), REPLACE(u.per_capita_income, '$', ''))
        AS per_capita_income,
    TRY_CONVERT(decimal(18,2), REPLACE(u.yearly_income, '$', ''))
        AS yearly_income,
    TRY_CONVERT(decimal(18,2), REPLACE(u.total_debt, '$', ''))
        AS total_debt,
    u.credit_score,
    u.num_credit_cards,
    c.card_brand,
    c.card_type,
    c.card_number,
    c.expires,
    c.cvv,
    c.has_chip,
    c.num_cards_issued,
    TRY_CONVERT(decimal(18,2), REPLACE(c.credit_limit, '$', ''))
        AS credit_limit,
    c.acct_open_date,
    c.year_pin_last_changed,
    c.card_on_dark_web,
    m.description AS mcc_description
FROM dbo.transactions_data AS t
INNER JOIN dbo.fraud_labels AS f
    ON f.transaction_id = t.id
INNER JOIN dbo.cards_data AS c
    ON c.id = t.card_id
   AND c.client_id = t.client_id
INNER JOIN dbo.users_data AS u
    ON u.id = t.client_id
LEFT JOIN dbo.mcc_codes AS m
    ON m.mcc = t.mcc;
GO
