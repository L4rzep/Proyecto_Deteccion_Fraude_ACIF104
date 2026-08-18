using System;
using System.Collections.Generic;
using System.Data;
using System.IO;
using System.Text;
using Microsoft.VisualBasic.FileIO;
using System.Linq;

namespace Proyecto_Deteccion_Fraude_ACIF104.Funciones
{
    public class GestorPlantillas
    {
        // Estructuras de las 5 tablas base
        private Dictionary<string, string[]> estructurasTablas = new Dictionary<string, string[]>()
        {
            { "transactions_data", new string[] { "transaction_id", "client_id", "card_id", "amount", "transaction_date", "use_chip", "mcc" } },
            { "users_data", new string[] { "client_id", "gender", "birth_date", "city", "state", "zipcode" } },
            { "cards_data", new string[] { "card_id", "client_id", "card_brand", "card_type", "expires", "cvv" } },
            { "fraud_labels", new string[] { "transaction_id", "is_fraud" } },
            { "mcc_codes", new string[] { "mcc", "mcc_description" } }
        };

        public string[] ObtenerListaTablas()
        {
            return new List<string>(estructurasTablas.Keys).ToArray();
        }

        // Exporta la plantilla CSV vacía
        public void ExportarPlantilla(string nombreTabla, string rutaArchivo)
        {
            if (!estructurasTablas.ContainsKey(nombreTabla))
                throw new Exception("Tabla no válida.");

            string encabezados = string.Join(",", estructurasTablas[nombreTabla]);
            File.WriteAllText(rutaArchivo, encabezados + Environment.NewLine, Encoding.UTF8);
        }

        // Lee un CSV y lo prepara para mostrarlo antes de cargarlo.
        public DataTable CargarCSV(string rutaArchivo)
        {
            DataTable dt = new DataTable();

            // Admite archivos separados por coma o punto y coma.
            string? primeraLinea = File.ReadLines(rutaArchivo).FirstOrDefault();
            string delimitador = (primeraLinea != null && primeraLinea.Contains(";") && !primeraLinea.Contains(",")) ? ";" : ",";

            using (TextFieldParser parser = new TextFieldParser(rutaArchivo))
            {
                parser.TextFieldType = FieldType.Delimited;
                parser.SetDelimiters(delimitador);
                parser.HasFieldsEnclosedInQuotes = true;

                // 1. Leer los encabezados
                if (!parser.EndOfData)
                {
                    string[] encabezados = parser.ReadFields() ?? Array.Empty<string>();
                    foreach (string col in encabezados)
                    {
                        string colLimpia = col.Trim().Replace("\"", "");
                        dt.Columns.Add(colLimpia);
                    }
                }

                // 2. Leer los datos fila por fila
                while (!parser.EndOfData)
                {
                    try
                    {
                        string[]? campos = parser.ReadFields();

                        // Asegurar que solo suban filas que estén perfectas (no rotas)
                        if (campos != null && campos.Length == dt.Columns.Count)
                        {
                            dt.Rows.Add(campos);
                        }
                    }
                    catch
                    {
                        // Si una fila del CSV está corrupta, la saltamos para que no colapse la carga
                        continue;
                    }
                }
            }

            return dt;
        }
    }
}
