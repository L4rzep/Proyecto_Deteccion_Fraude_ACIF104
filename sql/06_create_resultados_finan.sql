/*
    Persistencia idempotente de predicciones FINAN.
    Conserva los nombres usados por la aplicación histórica y agrega los
    metadatos necesarios para reproducibilidad y monitoreo.
*/
SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
SET ANSI_PADDING ON;
SET ANSI_WARNINGS ON;
SET CONCAT_NULL_YIELDS_NULL ON;
SET ARITHABORT ON;
SET NUMERIC_ROUNDABORT OFF;
SET NOCOUNT ON;
SET XACT_ABORT ON;
GO

IF OBJECT_ID(N'dbo.Resultados_Fraude_FINAN', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.Resultados_Fraude_FINAN
    (
        transaction_id       bigint          NOT NULL,
        is_fraud_predicted   bit             NOT NULL,
        fraud_probability    float           NOT NULL,
        threshold_used       float           NOT NULL,
        risk_level           nvarchar(20)    NOT NULL
            CONSTRAINT DF_finan_result_risk DEFAULT N'por confirmar',
        top_factors          nvarchar(max)   NULL,
        model_version        nvarchar(100)   NOT NULL,
        snapshot_version     nvarchar(100)   NOT NULL,
        run_id               uniqueidentifier NOT NULL
            CONSTRAINT DF_finan_result_run DEFAULT NEWID(),
        execution_id         uniqueidentifier NOT NULL
            CONSTRAINT DF_finan_result_execution DEFAULT NEWID(),
        fecha_analisis       datetime2(0)    NOT NULL
            CONSTRAINT DF_finan_result_timestamp DEFAULT SYSUTCDATETIME(),
        predicted_class      AS (is_fraud_predicted) PERSISTED,
        decision_threshold   AS (threshold_used) PERSISTED,
        prediction_timestamp AS (fecha_analisis) PERSISTED,
        CONSTRAINT PK_Resultados_Fraude_FINAN PRIMARY KEY (transaction_id),
        CONSTRAINT CK_finan_result_probability
            CHECK (fraud_probability >= 0.0 AND fraud_probability <= 1.0),
        CONSTRAINT CK_finan_result_threshold
            CHECK (threshold_used >= 0.0 AND threshold_used <= 1.0)
    );
END;
GO

/* Migración no destructiva para la tabla histórica si ya existe. */
IF COL_LENGTH(N'dbo.Resultados_Fraude_FINAN', N'snapshot_version') IS NULL
BEGIN
    ALTER TABLE dbo.Resultados_Fraude_FINAN
        ADD snapshot_version nvarchar(100) NOT NULL
            CONSTRAINT DF_finan_result_snapshot_legacy DEFAULT N'legacy';
END;
GO

IF COL_LENGTH(N'dbo.Resultados_Fraude_FINAN', N'execution_id') IS NULL
BEGIN
    ALTER TABLE dbo.Resultados_Fraude_FINAN
        ADD execution_id uniqueidentifier NOT NULL
            CONSTRAINT DF_finan_result_execution_legacy DEFAULT NEWID();
END;
GO

IF COL_LENGTH(N'dbo.Resultados_Fraude_FINAN', N'predicted_class') IS NULL
BEGIN
    ALTER TABLE dbo.Resultados_Fraude_FINAN
        ADD predicted_class AS (is_fraud_predicted) PERSISTED;
END;
GO

IF COL_LENGTH(N'dbo.Resultados_Fraude_FINAN', N'decision_threshold') IS NULL
BEGIN
    ALTER TABLE dbo.Resultados_Fraude_FINAN
        ADD decision_threshold AS (threshold_used) PERSISTED;
END;
GO

IF COL_LENGTH(N'dbo.Resultados_Fraude_FINAN', N'prediction_timestamp') IS NULL
BEGIN
    ALTER TABLE dbo.Resultados_Fraude_FINAN
        ADD prediction_timestamp AS (fecha_analisis) PERSISTED;
END;
GO

IF NOT EXISTS
(
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'dbo.Resultados_Fraude_FINAN')
      AND name = N'IX_Resultados_FINAN_Run'
)
BEGIN
    CREATE NONCLUSTERED INDEX IX_Resultados_FINAN_Run
        ON dbo.Resultados_Fraude_FINAN (run_id, model_version)
        INCLUDE (transaction_id, fraud_probability, is_fraud_predicted);
END;
GO

IF OBJECT_ID(N'dbo.Finan_Execution_Log', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.Finan_Execution_Log
    (
        execution_id       bigint IDENTITY(1, 1) NOT NULL,
        run_id             uniqueidentifier      NOT NULL,
        started_at         datetime2(0)          NOT NULL,
        processed_rows     bigint                NOT NULL,
        predicted_frauds   bigint                NOT NULL,
        threshold_used     float                 NOT NULL,
        elapsed_ms         bigint                NOT NULL,
        status             nvarchar(30)          NOT NULL,
        message            nvarchar(1000)        NULL,
        CONSTRAINT PK_Finan_Execution_Log PRIMARY KEY (execution_id)
    );
END;
GO
