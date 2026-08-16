/* Asignación persistente y trazable del snapshot oficial. */
SET NOCOUNT ON;
SET XACT_ABORT ON;
GO

IF OBJECT_ID(N'dbo.finan_split_assignment', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.finan_split_assignment
    (
        transaction_id   bigint         NOT NULL,
        snapshot_version nvarchar(100)  NOT NULL,
        split            varchar(10)    NOT NULL,
        seed             int            NOT NULL,
        created_at       datetime2(0)   NOT NULL
            CONSTRAINT DF_finan_split_created_at DEFAULT SYSUTCDATETIME(),
        CONSTRAINT PK_finan_split_assignment
            PRIMARY KEY CLUSTERED (snapshot_version, transaction_id),
        CONSTRAINT CK_finan_split_value
            CHECK (split IN ('train', 'validation', 'test'))
    );
END;
GO
IF NOT EXISTS
(
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'dbo.finan_split_assignment')
      AND name = N'IX_finan_split_lookup'
)
BEGIN
    CREATE NONCLUSTERED INDEX IX_finan_split_lookup
        ON dbo.finan_split_assignment (snapshot_version, split)
        INCLUDE (transaction_id, seed);
END;
GO
