using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Text.Json;
using System.Text.Json.Serialization;
using Microsoft.Data.SqlClient;

namespace Proyecto_Deteccion_Fraude_ACIF104.Funciones
{
    public sealed class FactorPrediccion
    {
        [JsonPropertyName("feature")]
        public string Feature { get; set; } = string.Empty;

        [JsonPropertyName("value")]
        public double Value { get; set; }

        [JsonPropertyName("contribution")]
        public double Contribution { get; set; }
    }

    public sealed class ResultadoPrediccion
    {
        [JsonPropertyName("status")]
        public string Status { get; set; } = string.Empty;

        [JsonPropertyName("source")]
        public string Source { get; set; } = string.Empty;

        [JsonPropertyName("transaction_id")]
        public JsonElement TransactionId { get; set; }

        [JsonPropertyName("fraud_probability")]
        public double FraudProbability { get; set; }

        [JsonPropertyName("threshold")]
        public double Threshold { get; set; }

        [JsonPropertyName("is_fraud_prediction")]
        public bool IsFraudPrediction { get; set; }

        [JsonPropertyName("risk_level")]
        public string RiskLevel { get; set; } = string.Empty;

        [JsonPropertyName("model_sha256")]
        public string ModelSha256 { get; set; } = string.Empty;

        [JsonPropertyName("top_factors")]
        public List<FactorPrediccion> TopFactors { get; set; } = new();
    }

    public sealed class NuevaTransaccion
    {
        [JsonPropertyName("client_id")]
        public int ClientId { get; set; }

        [JsonPropertyName("card_id")]
        public int CardId { get; set; }

        [JsonPropertyName("amount")]
        public decimal Amount { get; set; }

        [JsonPropertyName("transaction_date")]
        public string TransactionDate { get; set; } = string.Empty;

        [JsonPropertyName("use_chip")]
        public string UseChip { get; set; } = string.Empty;

        [JsonPropertyName("mcc")]
        public int Mcc { get; set; }
    }

    public class PythonEngine
    {
        private static string RuntimePath(string fileName)
        {
            return Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "runtime", fileName);
        }

        private static (string Server, string Database) ReadSqlTarget()
        {
            SqlConnectionStringBuilder builder = new(
                Properties.Settings.Default.CadenaConexion
            );
            if (string.IsNullOrWhiteSpace(builder.DataSource)
                || string.IsNullOrWhiteSpace(builder.InitialCatalog))
            {
                throw new InvalidOperationException(
                    "La conexión debe indicar el servidor y la base de datos."
                );
            }
            return (builder.DataSource, builder.InitialCatalog);
        }

        private static ProcessStartInfo BuildStartInfo()
        {
            string pythonPath = Properties.Settings.Default.RutaPython;
            if (string.IsNullOrWhiteSpace(pythonPath) || !File.Exists(pythonPath))
            {
                throw new FileNotFoundException(
                    "Configure la ruta del ejecutable de Python antes de usar FINAN.",
                    pythonPath
                );
            }

            string scriptPath = RuntimePath("predict_transaction.py");
            string modelPath = RuntimePath("finan_fraud_pipeline.joblib");
            string schemaPath = RuntimePath("finan_feature_schema.json");
            foreach (string requiredPath in new[] { scriptPath, modelPath, schemaPath })
            {
                if (!File.Exists(requiredPath))
                {
                    throw new FileNotFoundException(
                        "Falta un archivo del modelo en la carpeta runtime.",
                        requiredPath
                    );
                }
            }

            (string server, string database) = ReadSqlTarget();
            ProcessStartInfo start = new()
            {
                FileName = pythonPath,
                WorkingDirectory = AppDomain.CurrentDomain.BaseDirectory,
                UseShellExecute = false,
                CreateNoWindow = true,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
            };
            start.ArgumentList.Add(scriptPath);
            start.ArgumentList.Add("--explain");
            start.ArgumentList.Add("--server");
            start.ArgumentList.Add(server);
            start.ArgumentList.Add("--database");
            start.ArgumentList.Add(database);
            start.ArgumentList.Add("--driver");
            start.ArgumentList.Add("ODBC Driver 17 for SQL Server");
            start.ArgumentList.Add("--model-file");
            start.ArgumentList.Add(modelPath);
            start.ArgumentList.Add("--schema-file");
            start.ArgumentList.Add(schemaPath);
            return start;
        }

        private static ResultadoPrediccion Run(ProcessStartInfo start)
        {
            using Process process = Process.Start(start)
                ?? throw new InvalidOperationException("No fue posible iniciar Python.");
            string output = process.StandardOutput.ReadToEnd();
            string error = process.StandardError.ReadToEnd();
            process.WaitForExit();
            if (process.ExitCode != 0)
            {
                throw new InvalidOperationException(
                    string.IsNullOrWhiteSpace(error) ? output : error
                );
            }
            ResultadoPrediccion? result = JsonSerializer.Deserialize<ResultadoPrediccion>(
                output,
                new JsonSerializerOptions { PropertyNameCaseInsensitive = true }
            );
            if (result is null || !string.Equals(result.Status, "ok", StringComparison.OrdinalIgnoreCase))
            {
                throw new InvalidOperationException("Python no devolvió una predicción válida.");
            }
            return result;
        }

        public ResultadoPrediccion PredecirTransaccion(long transactionId)
        {
            ProcessStartInfo start = BuildStartInfo();
            start.ArgumentList.Add("--transaction-id");
            start.ArgumentList.Add(transactionId.ToString());
            return Run(start);
        }

        public ResultadoPrediccion PredecirNuevaTransaccion(NuevaTransaccion input)
        {
            string tempPath = Path.Combine(
                Path.GetTempPath(),
                $"finan-new-{Guid.NewGuid():N}.json"
            );
            try
            {
                File.WriteAllText(
                    tempPath,
                    JsonSerializer.Serialize(input),
                    new System.Text.UTF8Encoding(encoderShouldEmitUTF8Identifier: false)
                );
                ProcessStartInfo start = BuildStartInfo();
                start.ArgumentList.Add("--new-transaction-json");
                start.ArgumentList.Add(tempPath);
                return Run(start);
            }
            finally
            {
                if (File.Exists(tempPath))
                {
                    File.Delete(tempPath);
                }
            }
        }
    }
}
