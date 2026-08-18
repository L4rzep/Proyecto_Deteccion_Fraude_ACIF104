/*
    FINAN - conjunto etiquetado para EDA, entrenamiento y evaluación.

    Reutiliza exactamente las variables de dbo.vw_finan_features y agrega
    is_fraud únicamente mediante la tabla de etiquetas.
*/
SET NOCOUNT ON;
GO

CREATE OR ALTER VIEW dbo.vw_dataset_maestro
AS
SELECT
    v.transaction_id,
    v.transaction_date,
    v.transaction_hour,
    v.day_of_week,
    v.is_weekend,
    v.transaction_month,
    v.client_id,
    v.card_id,
    v.amount,
    v.use_chip,
    v.merchant_id,
    v.merchant_city,
    v.merchant_state,
    v.merchant_zip,
    v.mcc,
    v.current_age,
    v.age_at_transaction,
    v.retirement_age,
    v.gender,
    v.per_capita_income,
    v.yearly_income,
    v.total_debt,
    v.credit_score,
    v.num_credit_cards,
    v.card_brand,
    v.card_type,
    v.has_chip,
    v.num_cards_issued,
    v.credit_limit,
    v.account_open_month,
    v.account_open_year,
    v.years_since_pin_change,
    v.mcc_description,
    v.amount_to_credit_limit,
    v.amount_to_yearly_income,
    v.card_account_age_years,
    v.months_to_card_expiration,
    f.is_fraud
FROM dbo.vw_finan_features AS v
INNER JOIN dbo.fraud_labels AS f
    ON f.transaction_id = v.transaction_id;
GO
