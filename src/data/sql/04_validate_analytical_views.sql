/* FINAN - comprobación de las vistas analíticas. No modifica datos. */
SET NOCOUNT ON;
GO

SELECT
    v.TABLE_NAME AS objeto,
    COUNT(*) AS columnas
FROM INFORMATION_SCHEMA.COLUMNS AS v
WHERE v.TABLE_SCHEMA = 'dbo'
  AND v.TABLE_NAME IN ('vw_finan_features', 'vw_dataset_maestro')
GROUP BY v.TABLE_NAME
ORDER BY v.TABLE_NAME;
GO

SELECT
    CASE
        WHEN EXISTS
        (
            SELECT 1
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = 'dbo'
              AND TABLE_NAME IN
                  ('vw_finan_features', 'vw_dataset_maestro')
              AND COLUMN_NAME IN
                  ('address', 'latitude', 'longitude', 'card_number', 'cvv')
        )
        THEN 'REVISAR'
        ELSE 'OK'
    END AS control_datos_sensibles;
GO

SELECT
    COUNT_BIG(*) AS transacciones_integradas
FROM dbo.vw_finan_features;
GO

SELECT
    COUNT_BIG(*) AS transacciones_etiquetadas,
    SUM(CONVERT(bigint, is_fraud)) AS fraudes,
    CONVERT(decimal(12, 8),
        AVG(CONVERT(float, is_fraud))) AS proporcion_fraude
FROM dbo.vw_dataset_maestro;
GO

SELECT TOP (5)
    transaction_id,
    transaction_date,
    amount,
    use_chip,
    mcc,
    is_fraud
FROM dbo.vw_dataset_maestro
ORDER BY transaction_id;
GO
