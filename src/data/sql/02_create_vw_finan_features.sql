/*
    FINAN - vista analítica disponible antes de conocer la etiqueta.

    Mantiene nombres utilizados en los informes formativos y agrega variables
    derivadas reproducibles. Excluye datos personales o financieros directos:
    domicilio, coordenadas, número de tarjeta y CVV.
*/
SET NOCOUNT ON;
GO

CREATE OR ALTER VIEW dbo.vw_finan_features
AS
WITH base AS
(
    SELECT
        t.id AS transaction_id,
        t.[date] AS transaction_date,
        t.client_id,
        t.card_id,
        TRY_CONVERT(decimal(18, 2),
            REPLACE(REPLACE(t.amount, '$', ''), ',', '')) AS amount,
        t.use_chip,
        t.merchant_id,
        t.merchant_city,
        t.merchant_state,
        t.zip AS merchant_zip,
        t.mcc,
        u.current_age,
        u.retirement_age,
        u.birth_year,
        u.birth_month,
        u.gender,
        TRY_CONVERT(decimal(18, 2),
            REPLACE(REPLACE(u.per_capita_income, '$', ''), ',', ''))
            AS per_capita_income,
        TRY_CONVERT(decimal(18, 2),
            REPLACE(REPLACE(u.yearly_income, '$', ''), ',', ''))
            AS yearly_income,
        TRY_CONVERT(decimal(18, 2),
            REPLACE(REPLACE(u.total_debt, '$', ''), ',', ''))
            AS total_debt,
        u.credit_score,
        u.num_credit_cards,
        c.card_brand,
        c.card_type,
        LTRIM(RTRIM(c.has_chip)) AS has_chip,
        c.num_cards_issued,
        TRY_CONVERT(decimal(18, 2),
            REPLACE(REPLACE(c.credit_limit, '$', ''), ',', ''))
            AS credit_limit,
        TRY_CONVERT(int, LEFT(c.acct_open_date, 2)) AS account_open_month,
        TRY_CONVERT(int, RIGHT(c.acct_open_date, 4)) AS account_open_year,
        c.year_pin_last_changed,
        TRY_CONVERT(int, LEFT(c.expires, 2)) AS expiration_month,
        TRY_CONVERT(int, RIGHT(c.expires, 4)) AS expiration_year,
        m.description AS mcc_description
    FROM dbo.transactions_data AS t
    INNER JOIN dbo.cards_data AS c
        ON c.id = t.card_id
       AND c.client_id = t.client_id
    INNER JOIN dbo.users_data AS u
        ON u.id = t.client_id
    LEFT JOIN dbo.mcc_codes AS m
        ON m.mcc = t.mcc
)
SELECT
    transaction_id,
    transaction_date,
    DATEPART(hour, transaction_date) AS transaction_hour,
    ((DATEDIFF(day, CONVERT(date, '19000101'),
        CONVERT(date, transaction_date)) % 7) + 1) AS day_of_week,
    CONVERT(bit, CASE
        WHEN (DATEDIFF(day, CONVERT(date, '19000101'),
            CONVERT(date, transaction_date)) % 7) IN (5, 6)
        THEN 1 ELSE 0
    END) AS is_weekend,
    DATEPART(month, transaction_date) AS transaction_month,
    client_id,
    card_id,
    amount,
    use_chip,
    merchant_id,
    merchant_city,
    merchant_state,
    merchant_zip,
    mcc,
    current_age,
    CASE
        WHEN birth_year IS NULL THEN NULL
        ELSE DATEPART(year, transaction_date) - birth_year
             - CASE
                 WHEN birth_month IS NOT NULL
                  AND DATEPART(month, transaction_date) < birth_month
                 THEN 1 ELSE 0
               END
    END AS age_at_transaction,
    retirement_age,
    gender,
    per_capita_income,
    yearly_income,
    total_debt,
    credit_score,
    num_credit_cards,
    card_brand,
    card_type,
    has_chip,
    num_cards_issued,
    credit_limit,
    account_open_month,
    account_open_year,
    CASE
        WHEN year_pin_last_changed IS NULL
          OR year_pin_last_changed > DATEPART(year, transaction_date)
        THEN NULL
        ELSE DATEPART(year, transaction_date) - year_pin_last_changed
    END AS years_since_pin_change,
    mcc_description,
    TRY_CONVERT(decimal(18, 6),
        amount / NULLIF(credit_limit, 0)) AS amount_to_credit_limit,
    TRY_CONVERT(decimal(18, 6),
        amount / NULLIF(yearly_income, 0)) AS amount_to_yearly_income,
    CASE
        WHEN account_open_year IS NULL
          OR account_open_month NOT BETWEEN 1 AND 12
        THEN NULL
        ELSE DATEDIFF
        (
            month,
            DATEFROMPARTS(account_open_year, account_open_month, 1),
            transaction_date
        ) / 12.0
    END AS card_account_age_years,
    CASE
        WHEN expiration_year IS NULL
          OR expiration_month NOT BETWEEN 1 AND 12
        THEN NULL
        ELSE DATEDIFF
        (
            month,
            transaction_date,
            EOMONTH(DATEFROMPARTS(expiration_year, expiration_month, 1))
        )
    END AS months_to_card_expiration
FROM base;
GO
