/*
    FINAN - tablas fuente de FraudeDB.
    Esquema reconstruido desde los cinco archivos reales del dataset público.
    El script no elimina ni reemplaza tablas existentes.
*/
SET NOCOUNT ON;
SET XACT_ABORT ON;
GO

IF OBJECT_ID(N'dbo.users_data', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.users_data
    (
        id                  int            NOT NULL,
        current_age         int            NULL,
        retirement_age      int            NULL,
        birth_year          int            NULL,
        birth_month         int            NULL,
        gender              nvarchar(32)   NULL,
        address             nvarchar(255)  NULL,
        latitude            decimal(10, 6) NULL,
        longitude           decimal(10, 6) NULL,
        per_capita_income   varchar(32)    NULL,
        yearly_income       varchar(32)    NULL,
        total_debt          varchar(32)    NULL,
        credit_score        int            NULL,
        num_credit_cards    int            NULL,
        CONSTRAINT PK_users_data PRIMARY KEY CLUSTERED (id)
    );
END;
GO

IF OBJECT_ID(N'dbo.cards_data', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.cards_data
    (
        id                      int           NOT NULL,
        client_id               int           NOT NULL,
        card_brand              nvarchar(40)  NULL,
        card_type               nvarchar(40)  NULL,
        card_number             varchar(32)   NULL,
        expires                 varchar(16)   NULL,
        cvv                     varchar(8)    NULL,
        has_chip                varchar(8)    NULL,
        num_cards_issued        int           NULL,
        credit_limit            varchar(32)   NULL,
        acct_open_date          varchar(16)   NULL,
        year_pin_last_changed   int           NULL,
        card_on_dark_web        varchar(8)    NULL,
        CONSTRAINT PK_cards_data PRIMARY KEY CLUSTERED (id)
    );
END;
GO

IF OBJECT_ID(N'dbo.transactions_data', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.transactions_data
    (
        id               bigint         NOT NULL,
        [date]           datetime2(0)   NOT NULL,
        client_id        int            NOT NULL,
        card_id          int            NOT NULL,
        amount           varchar(32)    NOT NULL,
        use_chip         nvarchar(64)   NULL,
        merchant_id      bigint         NULL,
        merchant_city    nvarchar(160)  NULL,
        merchant_state   nvarchar(80)   NULL,
        zip              varchar(32)    NULL,
        mcc              int            NULL,
        errors           nvarchar(500)  NULL,
        CONSTRAINT PK_transactions_data PRIMARY KEY CLUSTERED (id)
    );
END;
GO

IF OBJECT_ID(N'dbo.fraud_labels', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.fraud_labels
    (
        transaction_id  bigint NOT NULL,
        is_fraud        bit    NOT NULL,
        CONSTRAINT PK_fraud_labels PRIMARY KEY CLUSTERED (transaction_id)
    );
END;
GO

IF OBJECT_ID(N'dbo.mcc_codes', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.mcc_codes
    (
        mcc          int            NOT NULL,
        description  nvarchar(255)  NOT NULL,
        CONSTRAINT PK_mcc_codes PRIMARY KEY CLUSTERED (mcc)
    );
END;
GO

/*
    Las relaciones se validan en src/data/validate_data.py. No se crean claves
    foráneas aquí porque el orden de carga del dataset debe permitir reanudación
    por tabla y porque no todas las transacciones poseen etiqueta.
*/
