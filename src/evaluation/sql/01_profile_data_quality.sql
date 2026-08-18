/*
    FINAN - perfil inicial de calidad del conjunto etiquetado.

    Consulta de solo lectura. No crea ni modifica tablas ni vistas.
    Entrega evidencia reproducible de tamaño, periodo, completitud y controles
    básicos antes del análisis de valores atípicos y del modelamiento.
*/
SET NOCOUNT ON;
GO

IF OBJECT_ID(N'dbo.vw_dataset_maestro', N'V') IS NULL
BEGIN
    THROW 50001,
        'No existe dbo.vw_dataset_maestro. Ejecute primero los SQL 02 y 03 de preparación de datos.',
        1;
END;
GO

/* 1. Tamaño, periodo y distribución de la variable objetivo. */
SELECT
    COUNT_BIG(*) AS total_etiquetadas,
    SUM(CONVERT(bigint, is_fraud)) AS fraudes,
    COUNT_BIG(*) - SUM(CONVERT(bigint, is_fraud)) AS no_fraudes,
    CONVERT(decimal(9, 6),
        100.0 * AVG(CONVERT(float, is_fraud))) AS porcentaje_fraude,
    MIN(transaction_date) AS primera_transaccion,
    MAX(transaction_date) AS ultima_transaccion
FROM dbo.vw_dataset_maestro;
GO

/* 2. Completitud de las 38 variables en una sola lectura de la vista. */
WITH perfil AS
(
    SELECT
        COUNT_BIG(*) AS total_filas,
        SUM(CONVERT(bigint, CASE WHEN transaction_id IS NULL THEN 1 ELSE 0 END)) AS n_transaction_id,
        SUM(CONVERT(bigint, CASE WHEN transaction_date IS NULL THEN 1 ELSE 0 END)) AS n_transaction_date,
        SUM(CONVERT(bigint, CASE WHEN transaction_hour IS NULL THEN 1 ELSE 0 END)) AS n_transaction_hour,
        SUM(CONVERT(bigint, CASE WHEN day_of_week IS NULL THEN 1 ELSE 0 END)) AS n_day_of_week,
        SUM(CONVERT(bigint, CASE WHEN is_weekend IS NULL THEN 1 ELSE 0 END)) AS n_is_weekend,
        SUM(CONVERT(bigint, CASE WHEN transaction_month IS NULL THEN 1 ELSE 0 END)) AS n_transaction_month,
        SUM(CONVERT(bigint, CASE WHEN client_id IS NULL THEN 1 ELSE 0 END)) AS n_client_id,
        SUM(CONVERT(bigint, CASE WHEN card_id IS NULL THEN 1 ELSE 0 END)) AS n_card_id,
        SUM(CONVERT(bigint, CASE WHEN amount IS NULL THEN 1 ELSE 0 END)) AS n_amount,
        SUM(CONVERT(bigint, CASE WHEN use_chip IS NULL THEN 1 ELSE 0 END)) AS n_use_chip,
        SUM(CONVERT(bigint, CASE WHEN merchant_id IS NULL THEN 1 ELSE 0 END)) AS n_merchant_id,
        SUM(CONVERT(bigint, CASE WHEN merchant_city IS NULL THEN 1 ELSE 0 END)) AS n_merchant_city,
        SUM(CONVERT(bigint, CASE WHEN merchant_state IS NULL THEN 1 ELSE 0 END)) AS n_merchant_state,
        SUM(CONVERT(bigint, CASE WHEN merchant_zip IS NULL THEN 1 ELSE 0 END)) AS n_merchant_zip,
        SUM(CONVERT(bigint, CASE WHEN mcc IS NULL THEN 1 ELSE 0 END)) AS n_mcc,
        SUM(CONVERT(bigint, CASE WHEN current_age IS NULL THEN 1 ELSE 0 END)) AS n_current_age,
        SUM(CONVERT(bigint, CASE WHEN age_at_transaction IS NULL THEN 1 ELSE 0 END)) AS n_age_at_transaction,
        SUM(CONVERT(bigint, CASE WHEN retirement_age IS NULL THEN 1 ELSE 0 END)) AS n_retirement_age,
        SUM(CONVERT(bigint, CASE WHEN gender IS NULL THEN 1 ELSE 0 END)) AS n_gender,
        SUM(CONVERT(bigint, CASE WHEN per_capita_income IS NULL THEN 1 ELSE 0 END)) AS n_per_capita_income,
        SUM(CONVERT(bigint, CASE WHEN yearly_income IS NULL THEN 1 ELSE 0 END)) AS n_yearly_income,
        SUM(CONVERT(bigint, CASE WHEN total_debt IS NULL THEN 1 ELSE 0 END)) AS n_total_debt,
        SUM(CONVERT(bigint, CASE WHEN credit_score IS NULL THEN 1 ELSE 0 END)) AS n_credit_score,
        SUM(CONVERT(bigint, CASE WHEN num_credit_cards IS NULL THEN 1 ELSE 0 END)) AS n_num_credit_cards,
        SUM(CONVERT(bigint, CASE WHEN card_brand IS NULL THEN 1 ELSE 0 END)) AS n_card_brand,
        SUM(CONVERT(bigint, CASE WHEN card_type IS NULL THEN 1 ELSE 0 END)) AS n_card_type,
        SUM(CONVERT(bigint, CASE WHEN has_chip IS NULL THEN 1 ELSE 0 END)) AS n_has_chip,
        SUM(CONVERT(bigint, CASE WHEN num_cards_issued IS NULL THEN 1 ELSE 0 END)) AS n_num_cards_issued,
        SUM(CONVERT(bigint, CASE WHEN credit_limit IS NULL THEN 1 ELSE 0 END)) AS n_credit_limit,
        SUM(CONVERT(bigint, CASE WHEN account_open_month IS NULL THEN 1 ELSE 0 END)) AS n_account_open_month,
        SUM(CONVERT(bigint, CASE WHEN account_open_year IS NULL THEN 1 ELSE 0 END)) AS n_account_open_year,
        SUM(CONVERT(bigint, CASE WHEN years_since_pin_change IS NULL THEN 1 ELSE 0 END)) AS n_years_since_pin_change,
        SUM(CONVERT(bigint, CASE WHEN mcc_description IS NULL THEN 1 ELSE 0 END)) AS n_mcc_description,
        SUM(CONVERT(bigint, CASE WHEN amount_to_credit_limit IS NULL THEN 1 ELSE 0 END)) AS n_amount_to_credit_limit,
        SUM(CONVERT(bigint, CASE WHEN amount_to_yearly_income IS NULL THEN 1 ELSE 0 END)) AS n_amount_to_yearly_income,
        SUM(CONVERT(bigint, CASE WHEN card_account_age_years IS NULL THEN 1 ELSE 0 END)) AS n_card_account_age_years,
        SUM(CONVERT(bigint, CASE WHEN months_to_card_expiration IS NULL THEN 1 ELSE 0 END)) AS n_months_to_card_expiration,
        SUM(CONVERT(bigint, CASE WHEN is_fraud IS NULL THEN 1 ELSE 0 END)) AS n_is_fraud
    FROM dbo.vw_dataset_maestro
)
SELECT
    v.variable,
    p.total_filas,
    v.filas_nulas,
    CONVERT(decimal(9, 6),
        100.0 * v.filas_nulas / NULLIF(p.total_filas, 0)) AS porcentaje_nulo
FROM perfil AS p
CROSS APPLY
(
    VALUES
        (N'transaction_id', p.n_transaction_id),
        (N'transaction_date', p.n_transaction_date),
        (N'transaction_hour', p.n_transaction_hour),
        (N'day_of_week', p.n_day_of_week),
        (N'is_weekend', p.n_is_weekend),
        (N'transaction_month', p.n_transaction_month),
        (N'client_id', p.n_client_id),
        (N'card_id', p.n_card_id),
        (N'amount', p.n_amount),
        (N'use_chip', p.n_use_chip),
        (N'merchant_id', p.n_merchant_id),
        (N'merchant_city', p.n_merchant_city),
        (N'merchant_state', p.n_merchant_state),
        (N'merchant_zip', p.n_merchant_zip),
        (N'mcc', p.n_mcc),
        (N'current_age', p.n_current_age),
        (N'age_at_transaction', p.n_age_at_transaction),
        (N'retirement_age', p.n_retirement_age),
        (N'gender', p.n_gender),
        (N'per_capita_income', p.n_per_capita_income),
        (N'yearly_income', p.n_yearly_income),
        (N'total_debt', p.n_total_debt),
        (N'credit_score', p.n_credit_score),
        (N'num_credit_cards', p.n_num_credit_cards),
        (N'card_brand', p.n_card_brand),
        (N'card_type', p.n_card_type),
        (N'has_chip', p.n_has_chip),
        (N'num_cards_issued', p.n_num_cards_issued),
        (N'credit_limit', p.n_credit_limit),
        (N'account_open_month', p.n_account_open_month),
        (N'account_open_year', p.n_account_open_year),
        (N'years_since_pin_change', p.n_years_since_pin_change),
        (N'mcc_description', p.n_mcc_description),
        (N'amount_to_credit_limit', p.n_amount_to_credit_limit),
        (N'amount_to_yearly_income', p.n_amount_to_yearly_income),
        (N'card_account_age_years', p.n_card_account_age_years),
        (N'months_to_card_expiration', p.n_months_to_card_expiration),
        (N'is_fraud', p.n_is_fraud)
) AS v(variable, filas_nulas)
ORDER BY v.variable;
GO

/*
    3. Controles que requieren revisión, no eliminación automática.
    Los montos negativos pueden representar devoluciones y se informan como
    una categoría válida hasta analizar su relación con el fraude.
*/
WITH controles AS
(
    SELECT
        SUM(CONVERT(bigint, CASE WHEN amount < 0 THEN 1 ELSE 0 END)) AS montos_negativos,
        SUM(CONVERT(bigint, CASE WHEN amount = 0 THEN 1 ELSE 0 END)) AS montos_cero,
        SUM(CONVERT(bigint, CASE WHEN age_at_transaction NOT BETWEEN 0 AND 120 THEN 1 ELSE 0 END)) AS edades_fuera_rango,
        SUM(CONVERT(bigint, CASE WHEN credit_score NOT BETWEEN 300 AND 850 THEN 1 ELSE 0 END)) AS puntajes_fuera_rango,
        SUM(CONVERT(bigint, CASE WHEN card_account_age_years < 0 THEN 1 ELSE 0 END)) AS cuentas_previas_inconsistentes,
        SUM(CONVERT(bigint, CASE WHEN months_to_card_expiration < 0 THEN 1 ELSE 0 END)) AS tarjetas_vencidas,
        SUM(CONVERT(bigint, CASE WHEN yearly_income <= 0 THEN 1 ELSE 0 END)) AS ingresos_no_positivos,
        SUM(CONVERT(bigint, CASE WHEN credit_limit <= 0 THEN 1 ELSE 0 END)) AS limites_no_positivos
    FROM dbo.vw_dataset_maestro
)
SELECT
    v.control,
    v.filas_detectadas,
    v.interpretacion
FROM controles AS c
CROSS APPLY
(
    VALUES
        (N'montos_negativos', c.montos_negativos, N'Revisar como posibles devoluciones; no eliminar automáticamente'),
        (N'montos_cero', c.montos_cero, N'Revisar su significado operativo'),
        (N'edades_fuera_rango', c.edades_fuera_rango, N'Edad calculada menor que 0 o mayor que 120'),
        (N'puntajes_fuera_rango', c.puntajes_fuera_rango, N'Puntaje fuera del intervalo 300 a 850'),
        (N'cuentas_previas_inconsistentes', c.cuentas_previas_inconsistentes, N'Cuenta abierta después de la transacción'),
        (N'tarjetas_vencidas', c.tarjetas_vencidas, N'Vencimiento anterior a la transacción; requiere revisión'),
        (N'ingresos_no_positivos', c.ingresos_no_positivos, N'Ingreso anual igual o menor que cero'),
        (N'limites_no_positivos', c.limites_no_positivos, N'Límite de crédito igual o menor que cero')
) AS v(control, filas_detectadas, interpretacion)
ORDER BY v.control;
GO
