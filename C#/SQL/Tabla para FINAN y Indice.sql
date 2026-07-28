SELECT *FROM cards_data
SELECT *FROM fraud_labels
SELECT *FROM mcc_codes
SELECT *FROM transactions_data
SELECT *FROM users_data


-- 1. Borrar la tabla vieja/automática si existe
DROP TABLE IF EXISTS Resultados_Fraude_FINAN;
GO

-- 2. Crear la tabla oficial súper optimizada para FINAN
CREATE TABLE Resultados_Fraude_FINAN (
    transaction_id INT PRIMARY KEY,
    is_fraud_predicted BIT NOT NULL,
    fraud_probability FLOAT NOT NULL,
    fecha_analisis DATETIME DEFAULT GETDATE()
);
GO

-- 3. Índice para acelerar las búsquedas al máximo
CREATE NONCLUSTERED INDEX IX_Resultados_FINAN_ID 
ON Resultados_Fraude_FINAN (transaction_id);
GO