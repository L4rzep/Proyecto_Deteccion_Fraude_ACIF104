using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;

namespace Proyecto_Deteccion_Fraude_ACIF104.Funciones
{
    public class PythonEngine
    {
        // Llama a analisis_fraude.py enviándole los argumentos de rango (inicio y fin)
        public string EjecutarModeloInferencia(int idInicio, int idFin)
        {
            string rutaPython = Properties.Settings.Default.RutaPython;
            string rutaScript = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "analisis_fraude.py");

            if (string.IsNullOrEmpty(rutaPython) || !File.Exists(rutaPython))
            {
                MessageBox.Show("Ruta de Python no configurada. Edítela en la pestaña Configuración.", "Atención", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return "Error: Ruta de Python no válida";
            }

            try
            {
                ProcessStartInfo start = new ProcessStartInfo
                {
                    FileName = rutaPython,
                    Arguments = $"\"{rutaScript}\" {idInicio} {idFin}",
                    UseShellExecute = false,
                    CreateNoWindow = true,
                    RedirectStandardOutput = true,
                    RedirectStandardError = true
                };

                using (Process process = Process.Start(start))
                {
                    string salida = process.StandardOutput.ReadToEnd();
                    string error = process.StandardError.ReadToEnd();
                    process.WaitForExit();

                    return string.IsNullOrEmpty(error) ? salida : $"Salida: {salida}\nLog: {error}";
                }
            }
            catch (Exception ex)
            {
                return $"Exception: {ex.Message}";
            }
        }
    }
}