using System.Text.Json;

namespace Proyecto_Deteccion_Fraude_ACIF104.Funciones
{
    public sealed class PredictionMonitor
    {
        private sealed class Entry
        {
            public DateTime Timestamp { get; set; }
            public string Source { get; set; } = string.Empty;
            public bool Success { get; set; }
            public bool Alert { get; set; }
            public double? Probability { get; set; }
            public string Risk { get; set; } = string.Empty;
            public long DurationMs { get; set; }
            public string ModelSha256 { get; set; } = string.Empty;
            public string Message { get; set; } = string.Empty;
        }

        private static readonly object FileLock = new();

        public string LogPath { get; } = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "FINAN",
            "prediction_monitoring.jsonl"
        );

        public void RegisterSuccess(ResultadoPrediccion result, long durationMs)
        {
            Append(new Entry
            {
                Timestamp = DateTime.Now,
                Source = result.Source,
                Success = true,
                Alert = result.IsFraudPrediction,
                Probability = result.FraudProbability,
                Risk = result.RiskLevel,
                DurationMs = durationMs,
                ModelSha256 = result.ModelSha256,
            });
        }

        public void RegisterError(string source, long durationMs, string message)
        {
            Append(new Entry
            {
                Timestamp = DateTime.Now,
                Source = source,
                Success = false,
                DurationMs = durationMs,
                Message = message,
            });
        }

        public string GetSummary()
        {
            if (!File.Exists(LogPath)) return "Monitoreo: 0 evaluaciones.";

            int total = 0;
            int alerts = 0;
            int errors = 0;
            long totalDuration = 0;
            foreach (string line in File.ReadLines(LogPath))
            {
                try
                {
                    Entry? entry = JsonSerializer.Deserialize<Entry>(line);
                    if (entry is null) continue;
                    total++;
                    if (entry.Alert) alerts++;
                    if (!entry.Success) errors++;
                    totalDuration += entry.DurationMs;
                }
                catch (JsonException)
                {
                    // Una línea incompleta no impide leer el resto del registro.
                }
            }

            long averageMs = total == 0 ? 0 : totalDuration / total;
            return $"Monitoreo: {total} evaluaciones, {alerts} alertas, "
                + $"{errors} errores, promedio {averageMs} ms.";
        }

        private void Append(Entry entry)
        {
            string? directory = Path.GetDirectoryName(LogPath);
            if (directory is null) return;
            Directory.CreateDirectory(directory);
            string line = JsonSerializer.Serialize(entry) + Environment.NewLine;
            lock (FileLock)
            {
                File.AppendAllText(
                    LogPath,
                    line,
                    new System.Text.UTF8Encoding(encoderShouldEmitUTF8Identifier: false)
                );
            }
        }
    }
}
