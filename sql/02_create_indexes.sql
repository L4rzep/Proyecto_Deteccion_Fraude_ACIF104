/* Índices observados o justificados por los joins y consultas oficiales. */
SET NOCOUNT ON;
SET XACT_ABORT ON;
GO

IF NOT EXISTS
(
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'dbo.cards_data')
      AND name = N'IX_cards_client'
)
BEGIN
    CREATE NONCLUSTERED INDEX IX_cards_client
        ON dbo.cards_data (client_id)
        INCLUDE (id, card_brand, card_type, has_chip, credit_limit);
END;
GO
IF NOT EXISTS
(
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'dbo.transactions_data')
      AND name = N'IX_transactions_client_card'
)
BEGIN
    /* Acelera la relación transacción-tarjeta y consultas por cliente. */
    CREATE NONCLUSTERED INDEX IX_transactions_client_card
        ON dbo.transactions_data (client_id, card_id)
        INCLUDE (id, [date], mcc);
END;
GO

IF NOT EXISTS
(
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'dbo.transactions_data')
      AND name = N'IX_transactions_mcc'
)
BEGIN
    /* Acelera perfiles y cruces con el catálogo MCC. */
    CREATE NONCLUSTERED INDEX IX_transactions_mcc
        ON dbo.transactions_data (mcc)
        INCLUDE (id);
END;
GO
