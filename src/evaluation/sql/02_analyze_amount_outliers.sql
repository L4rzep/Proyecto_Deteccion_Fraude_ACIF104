/*
    FINAN - análisis reproducible de montos y valores atípicos.

    Consulta de solo lectura. Los límites se calculan con el criterio IQR
    aplicado al valor absoluto del monto para considerar compras y devoluciones.
    Detectar un atípico no implica eliminarlo.
*/
SET NOCOUNT ON;
GO

IF OBJECT_ID(N'dbo.vw_dataset_maestro', N'V') IS NULL
BEGIN
    THROW 50002,
        'No existe dbo.vw_dataset_maestro. Ejecute primero los SQL 02 y 03 de preparación de datos.',
        1;
END;
GO

/* 1. Estadísticas descriptivas del monto según la etiqueta. */
SELECT
    is_fraud,
    COUNT_BIG(*) AS filas,
    MIN(amount) AS monto_minimo,
    CONVERT(decimal(18, 2), AVG(amount)) AS monto_promedio,
    MAX(amount) AS monto_maximo,
    SUM(CONVERT(bigint, CASE WHEN amount < 0 THEN 1 ELSE 0 END)) AS montos_negativos,
    SUM(CONVERT(bigint, CASE WHEN amount = 0 THEN 1 ELSE 0 END)) AS montos_cero
FROM dbo.vw_dataset_maestro
WHERE amount IS NOT NULL
GROUP BY is_fraud
ORDER BY is_fraud;
GO

/*
    2. Cuartiles del valor absoluto y límite superior de Tukey.
    Se usa ABS(amount) porque un reembolso negativo también puede tener una
    magnitud excepcional. El límite inferior se fija en cero por definición.
*/
DECLARE @q1 float;
DECLARE @mediana float;
DECLARE @q3 float;
DECLARE @limite_superior float;

WITH montos AS
(
    SELECT ABS(CONVERT(float, amount)) AS monto_absoluto
    FROM dbo.vw_dataset_maestro
    WHERE amount IS NOT NULL
),
percentiles AS
(
    SELECT
        PERCENTILE_CONT(0.25) WITHIN GROUP
            (ORDER BY monto_absoluto) OVER () AS q1,
        PERCENTILE_CONT(0.50) WITHIN GROUP
            (ORDER BY monto_absoluto) OVER () AS mediana,
        PERCENTILE_CONT(0.75) WITHIN GROUP
            (ORDER BY monto_absoluto) OVER () AS q3
    FROM montos
)
SELECT TOP (1)
    @q1 = q1,
    @mediana = mediana,
    @q3 = q3
FROM percentiles;

SET @limite_superior = @q3 + 1.5 * (@q3 - @q1);

SELECT
    CONVERT(decimal(18, 2), @q1) AS q1_monto_absoluto,
    CONVERT(decimal(18, 2), @mediana) AS mediana_monto_absoluto,
    CONVERT(decimal(18, 2), @q3) AS q3_monto_absoluto,
    CONVERT(decimal(18, 2), @limite_superior) AS limite_superior_iqr;

/* 3. Comparación entre montos habituales y atípicos. */
SELECT
    CASE
        WHEN ABS(CONVERT(float, amount)) > @limite_superior
        THEN N'Atípico por IQR'
        ELSE N'Dentro del límite IQR'
    END AS grupo_monto,
    COUNT_BIG(*) AS transacciones,
    SUM(CONVERT(bigint, is_fraud)) AS fraudes,
    CONVERT(decimal(9, 6),
        100.0 * AVG(CONVERT(float, is_fraud))) AS porcentaje_fraude
FROM dbo.vw_dataset_maestro
WHERE amount IS NOT NULL
GROUP BY
    CASE
        WHEN ABS(CONVERT(float, amount)) > @limite_superior
        THEN N'Atípico por IQR'
        ELSE N'Dentro del límite IQR'
    END
ORDER BY grupo_monto;
GO
