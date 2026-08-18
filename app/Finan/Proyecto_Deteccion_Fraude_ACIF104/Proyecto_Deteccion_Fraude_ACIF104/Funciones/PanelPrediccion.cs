using System;
using System.Drawing;
using System.Diagnostics;
using System.Globalization;
using System.Linq;
using System.Threading.Tasks;
using System.Windows.Forms;

namespace Proyecto_Deteccion_Fraude_ACIF104.Funciones
{
    public sealed class PanelPrediccion : UserControl
    {
        private readonly PythonEngine pythonEngine;
        private readonly DatabaseManager databaseManager;
        private readonly PredictionMonitor monitor = new();
        private readonly TextBox transactionId = new() { Width = 150, Text = "7984042" };
        private readonly NumericUpDown clientId = new() { Width = 110, Maximum = int.MaxValue };
        private readonly NumericUpDown cardId = new() { Width = 110, Maximum = int.MaxValue };
        private readonly NumericUpDown amount = new()
        {
            Width = 110,
            Minimum = -1_000_000_000,
            Maximum = 1_000_000_000,
            DecimalPlaces = 2,
        };
        private readonly DateTimePicker transactionDate = new()
        {
            Width = 170,
            Format = DateTimePickerFormat.Custom,
            CustomFormat = "yyyy-MM-dd HH:mm",
        };
        private readonly ComboBox useChip = new()
        {
            Width = 170,
            DropDownStyle = ComboBoxStyle.DropDownList,
        };
        private readonly NumericUpDown mcc = new()
        {
            Width = 100,
            Minimum = 0,
            Maximum = 9999,
        };
        private readonly Button analyzeExisting = new() { Text = "Analizar ID", AutoSize = true };
        private readonly Button loadAsNew = new() { Text = "Usar como ejemplo nuevo", AutoSize = true };
        private readonly Button analyzeNew = new() { Text = "Analizar nueva transacción", AutoSize = true };
        private readonly Label status = new()
        {
            Text = "Listo para analizar.",
            AutoSize = true,
            ForeColor = Color.Silver,
        };
        private readonly Label decision = new()
        {
            Text = "Sin evaluación",
            AutoSize = true,
            Font = new Font("Segoe UI", 15, FontStyle.Bold),
            ForeColor = Color.White,
        };
        private readonly Label probability = new() { AutoSize = true, ForeColor = Color.White };
        private readonly Label threshold = new() { AutoSize = true, ForeColor = Color.White };
        private readonly Label risk = new() { AutoSize = true, ForeColor = Color.White };
        private readonly DataGridView factors = new()
        {
            Dock = DockStyle.Fill,
            Height = 180,
            ReadOnly = true,
            AllowUserToAddRows = false,
            AllowUserToDeleteRows = false,
            AutoSizeColumnsMode = DataGridViewAutoSizeColumnsMode.Fill,
            BackgroundColor = Color.FromArgb(30, 41, 59),
            BorderStyle = BorderStyle.None,
        };

        public PanelPrediccion(PythonEngine pythonEngine, DatabaseManager databaseManager)
        {
            this.pythonEngine = pythonEngine;
            this.databaseManager = databaseManager;
            Dock = DockStyle.Fill;
            BackColor = Color.FromArgb(15, 23, 42);
            AutoScroll = true;
            useChip.Items.AddRange(
                new object[]
                {
                    "Chip Transaction",
                    "Swipe Transaction",
                    "Online Transaction",
                }
            );
            useChip.SelectedIndex = 0;
            factors.Columns.Add("factor", "Factor explicativo");
            factors.Columns.Add("effect", "Efecto en el riesgo");
            BuildLayout();
            analyzeExisting.Click += AnalyzeExisting_Click;
            loadAsNew.Click += LoadAsNew_Click;
            analyzeNew.Click += AnalyzeNew_Click;
        }

        private static Label FieldLabel(string text)
        {
            return new Label
            {
                Text = text,
                AutoSize = true,
                ForeColor = Color.White,
                Margin = new Padding(10, 8, 4, 0),
            };
        }

        private static GroupBox Group(string title)
        {
            return new GroupBox
            {
                Text = title,
                Dock = DockStyle.Fill,
                ForeColor = Color.DeepSkyBlue,
                Padding = new Padding(12),
                BackColor = Color.FromArgb(15, 23, 42),
            };
        }

        private void BuildLayout()
        {
            TableLayoutPanel root = new()
            {
                Dock = DockStyle.Top,
                Height = 700,
                Padding = new Padding(18),
                ColumnCount = 1,
                RowCount = 4,
            };
            root.RowStyles.Add(new RowStyle(SizeType.Absolute, 55));
            root.RowStyles.Add(new RowStyle(SizeType.Absolute, 105));
            root.RowStyles.Add(new RowStyle(SizeType.Absolute, 155));
            root.RowStyles.Add(new RowStyle(SizeType.Absolute, 350));

            Label title = new()
            {
                Text = "Evaluación de transacciones con FINAN",
                Dock = DockStyle.Fill,
                Font = new Font("Segoe UI", 18, FontStyle.Bold),
                ForeColor = Color.White,
                TextAlign = ContentAlignment.MiddleLeft,
            };
            root.Controls.Add(title, 0, 0);

            GroupBox existingGroup = Group("Comprobar una transacción existente");
            FlowLayoutPanel existingFlow = new()
            {
                Dock = DockStyle.Fill,
                FlowDirection = FlowDirection.LeftToRight,
                WrapContents = true,
            };
            existingFlow.Controls.Add(FieldLabel("ID de transacción:"));
            existingFlow.Controls.Add(transactionId);
            existingFlow.Controls.Add(analyzeExisting);
            existingFlow.Controls.Add(loadAsNew);
            existingGroup.Controls.Add(existingFlow);
            root.Controls.Add(existingGroup, 0, 1);

            GroupBox newGroup = Group("Ingresar una transacción nueva");
            FlowLayoutPanel newFlow = new()
            {
                Dock = DockStyle.Fill,
                FlowDirection = FlowDirection.LeftToRight,
                WrapContents = true,
                AutoScroll = true,
            };
            newFlow.Controls.Add(FieldLabel("Cliente:"));
            newFlow.Controls.Add(clientId);
            newFlow.Controls.Add(FieldLabel("Tarjeta:"));
            newFlow.Controls.Add(cardId);
            newFlow.Controls.Add(FieldLabel("Monto:"));
            newFlow.Controls.Add(amount);
            newFlow.Controls.Add(FieldLabel("Fecha:"));
            newFlow.Controls.Add(transactionDate);
            newFlow.Controls.Add(FieldLabel("Canal:"));
            newFlow.Controls.Add(useChip);
            newFlow.Controls.Add(FieldLabel("MCC:"));
            newFlow.Controls.Add(mcc);
            newFlow.Controls.Add(analyzeNew);
            newGroup.Controls.Add(newFlow);
            root.Controls.Add(newGroup, 0, 2);

            GroupBox resultGroup = Group("Resultado explicado");
            TableLayoutPanel resultLayout = new()
            {
                Dock = DockStyle.Fill,
                ColumnCount = 1,
                RowCount = 6,
            };
            resultLayout.RowStyles.Add(new RowStyle(SizeType.Absolute, 38));
            resultLayout.RowStyles.Add(new RowStyle(SizeType.Absolute, 25));
            resultLayout.RowStyles.Add(new RowStyle(SizeType.Absolute, 25));
            resultLayout.RowStyles.Add(new RowStyle(SizeType.Absolute, 25));
            resultLayout.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
            resultLayout.RowStyles.Add(new RowStyle(SizeType.Absolute, 25));
            resultLayout.Controls.Add(decision, 0, 0);
            resultLayout.Controls.Add(probability, 0, 1);
            resultLayout.Controls.Add(threshold, 0, 2);
            resultLayout.Controls.Add(risk, 0, 3);
            resultLayout.Controls.Add(factors, 0, 4);
            resultLayout.Controls.Add(status, 0, 5);
            resultGroup.Controls.Add(resultLayout);
            root.Controls.Add(resultGroup, 0, 3);
            Controls.Add(root);
        }

        private bool TryReadTransactionId(out long value)
        {
            if (long.TryParse(transactionId.Text.Trim(), out value) && value > 0)
            {
                return true;
            }
            MessageBox.Show(
                "Ingrese un ID de transacción válido.",
                "Dato requerido",
                MessageBoxButtons.OK,
                MessageBoxIcon.Warning
            );
            return false;
        }

        private async void AnalyzeExisting_Click(object? sender, EventArgs e)
        {
            if (!TryReadTransactionId(out long value)) return;
            await RunPrediction(
                "database",
                () => pythonEngine.PredecirTransaccion(value)
            );
        }

        private async void LoadAsNew_Click(object? sender, EventArgs e)
        {
            if (!TryReadTransactionId(out long value)) return;
            SetBusy(true, "Cargando los datos básicos desde SQL Server...");
            try
            {
                NuevaTransaccion input = await Task.Run(
                    () => databaseManager.ObtenerDatosBaseTransaccion(value)
                );
                clientId.Value = input.ClientId;
                cardId.Value = input.CardId;
                amount.Value = Math.Min(amount.Maximum, Math.Max(amount.Minimum, input.Amount));
                transactionDate.Value = DateTime.ParseExact(
                    input.TransactionDate,
                    "yyyy-MM-ddTHH:mm:ss",
                    CultureInfo.InvariantCulture
                );
                useChip.SelectedItem = input.UseChip;
                if (useChip.SelectedIndex < 0) useChip.Text = input.UseChip;
                mcc.Value = input.Mcc;
                status.Text = "Ejemplo cargado. Puede modificar sus valores antes de analizarlo.";
            }
            catch (Exception ex)
            {
                ShowError(ex);
            }
            finally
            {
                SetBusy(false);
            }
        }

        private async void AnalyzeNew_Click(object? sender, EventArgs e)
        {
            if (clientId.Value <= 0 || cardId.Value <= 0 || useChip.SelectedItem is null)
            {
                MessageBox.Show(
                    "Complete cliente, tarjeta y canal.",
                    "Datos requeridos",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Warning
                );
                return;
            }
            NuevaTransaccion input = new()
            {
                ClientId = decimal.ToInt32(clientId.Value),
                CardId = decimal.ToInt32(cardId.Value),
                Amount = amount.Value,
                TransactionDate = transactionDate.Value.ToString(
                    "yyyy-MM-ddTHH:mm:ss",
                    CultureInfo.InvariantCulture
                ),
                UseChip = Convert.ToString(useChip.SelectedItem) ?? string.Empty,
                Mcc = decimal.ToInt32(mcc.Value),
            };
            await RunPrediction(
                "new_transaction",
                () => pythonEngine.PredecirNuevaTransaccion(input)
            );
        }

        private async Task RunPrediction(
            string source,
            Func<ResultadoPrediccion> operation
        )
        {
            Stopwatch timer = Stopwatch.StartNew();
            SetBusy(true, "FINAN está calculando la predicción y su explicación...");
            try
            {
                ResultadoPrediccion result = await Task.Run(operation);
                timer.Stop();
                monitor.RegisterSuccess(result, timer.ElapsedMilliseconds);
                DisplayResult(result);
                status.Text = "Predicción completada. " + monitor.GetSummary();
            }
            catch (Exception ex)
            {
                timer.Stop();
                monitor.RegisterError(
                    source,
                    timer.ElapsedMilliseconds,
                    FriendlyError(ex.Message)
                );
                ShowError(ex);
            }
            finally
            {
                SetBusy(false);
            }
        }

        private void SetBusy(bool busy, string? message = null)
        {
            analyzeExisting.Enabled = !busy;
            loadAsNew.Enabled = !busy;
            analyzeNew.Enabled = !busy;
            Cursor = busy ? Cursors.WaitCursor : Cursors.Default;
            if (!string.IsNullOrWhiteSpace(message)) status.Text = message;
        }

        private void DisplayResult(ResultadoPrediccion result)
        {
            decision.Text = result.IsFraudPrediction
                ? "ALERTA: posible fraude"
                : "Sin alerta de fraude";
            decision.ForeColor = result.IsFraudPrediction
                ? Color.FromArgb(244, 63, 94)
                : Color.FromArgb(74, 222, 128);
            probability.Text = $"Probabilidad estimada: {result.FraudProbability:P2}";
            threshold.Text = $"Umbral de decisión validado: {result.Threshold:P2}";
            risk.Text = $"Nivel de riesgo: {TranslateRisk(result.RiskLevel)}";
            factors.Rows.Clear();
            foreach (FactorPrediccion factor in result.TopFactors)
            {
                factors.Rows.Add(
                    TranslateFeature(factor.Feature),
                    factor.Contribution >= 0
                        ? $"Aumenta el riesgo ({factor.Contribution:F4})"
                        : $"Reduce el riesgo ({Math.Abs(factor.Contribution):F4})"
                );
            }
        }

        private static string TranslateRisk(string value)
        {
            return value.ToLowerInvariant() switch
            {
                "alto" => "Alto",
                "medio" => "Medio",
                "bajo" => "Bajo",
                _ => value,
            };
        }

        private static string TranslateFeature(string value)
        {
            if (value.StartsWith("use_chip=", StringComparison.Ordinal))
                return "Canal: " + value["use_chip=".Length..];
            if (value.StartsWith("card_type=", StringComparison.Ordinal))
                return "Tipo de tarjeta: " + value["card_type=".Length..];
            if (value.StartsWith("card_brand=", StringComparison.Ordinal))
                return "Marca de tarjeta: " + value["card_brand=".Length..];
            if (value.StartsWith("mcc=", StringComparison.Ordinal))
                return "Categoría comercial MCC " + value["mcc=".Length..];
            return value switch
            {
                "amount" => "Monto de la transacción",
                "amount_to_credit_limit" => "Monto respecto del límite de crédito",
                "amount_to_yearly_income" => "Monto respecto del ingreso anual",
                "credit_limit" => "Límite de crédito",
                "yearly_income" => "Ingreso anual",
                "day_of_week=7" => "Día de la semana: domingo",
                _ => value.Replace('_', ' '),
            };
        }

        private static string FriendlyError(string message)
        {
            string lastLine = message
                .Split(new[] { '\r', '\n' }, StringSplitOptions.RemoveEmptyEntries)
                .LastOrDefault() ?? "No fue posible completar la operación.";
            int separator = lastLine.IndexOf(':');
            if (separator >= 0 && separator < lastLine.Length - 1)
            {
                lastLine = lastLine[(separator + 1)..].Trim();
            }
            return lastLine.Length <= 250
                ? lastLine
                : "El motor de predicción informó un error.";
        }

        private static void ShowError(Exception ex)
        {
            MessageBox.Show(
                FriendlyError(ex.Message),
                "No fue posible completar la predicción",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error
            );
        }
    }
}
