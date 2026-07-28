using System;
using System.Collections.Generic;
using System.Text;

namespace Proyecto_Deteccion_Fraude_ACIF104.Funciones
{
    internal class Configuracion
    {
        public static string CadenaConexion { get; set; } = @"Server=(localdb)\MSSQLLocalDB;Database=FraudeDB;Trusted_Connection=True;";
        public static string RutaPython { get; set; } = @"C:\Python314\python.exe";
        public static decimal UmbralFraude { get; set; } = 0.50m;
    }
}
