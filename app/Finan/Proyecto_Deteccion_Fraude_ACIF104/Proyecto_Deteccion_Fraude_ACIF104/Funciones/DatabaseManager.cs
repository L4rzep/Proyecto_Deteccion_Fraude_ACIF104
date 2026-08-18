using System;
using System.Data;
using System.Globalization;
using Microsoft.Data.SqlClient;
using System.Windows.Forms;

namespace Proyecto_Deteccion_Fraude_ACIF104.Funciones
{
    public class DatabaseManager
    {
        // Lee la cadena de conexión desde las configuraciones guardadas
        private string ObtenerCadenaConexion()
        {
            return Properties.Settings.Default.CadenaConexion;
        }

        // Probar si la base de datos responde
        public bool ProbarConexion(string cadenaPrueba)
        {
            try
            {
                using (SqlConnection conn = new SqlConnection(cadenaPrueba))
                {
                    conn.Open();
                    return true;
                }
            }
            catch (Exception ex)
            {
                MessageBox.Show($"Error al conectar con SQL Server: {ex.Message}", "Error SQL", MessageBoxButtons.OK, MessageBoxIcon.Error);
                return false;
            }
        }

        // Obtiene el ID más alto que ya pasó por la IA FINAN
        public int ObtenerUltimoIDProcesado()
        {
            try
            {
                using (SqlConnection conn = new SqlConnection(ObtenerCadenaConexion()))
                {
                    conn.Open();
                    // Busca el máximo ID en la tabla de resultados. Si está vacía, devuelve 0.
                    string query = "SELECT ISNULL(MAX(transaction_id), 0) FROM Resultados_Fraude_FINAN";
                    using (SqlCommand cmd = new SqlCommand(query, conn))
                    {
                        return Convert.ToInt32(cmd.ExecuteScalar());
                    }
                }
            }
            catch
            {
                return 0; // Si la tabla no existe aún, empezamos desde cero
            }
        }

        // Obtiene el ID más alto de todas las transacciones cargadas
        public int ObtenerMaximoIDTransacciones()
        {
            try
            {
                using (SqlConnection conn = new SqlConnection(ObtenerCadenaConexion()))
                {
                    conn.Open();
                    string query = "SELECT ISNULL(MAX(id), 0) FROM transactions_data";
                    using (SqlCommand cmd = new SqlCommand(query, conn))
                    {
                        return Convert.ToInt32(cmd.ExecuteScalar());
                    }
                }
            }
            catch
            {
                return 0;
            }
        }

        // Obtener datos con paginación de a 1000 registros para TC_Explo
        public DataTable ObtenerDatosPaginados(string nombreTabla, int pagina, int tamanoPagina = 1000)
        {
            DataTable dt = new DataTable();
            int offset = (pagina - 1) * tamanoPagina;

            string query = $"SELECT * FROM {nombreTabla} ORDER BY 1 OFFSET @Offset ROWS FETCH NEXT @Limite ROWS ONLY;";

            try
            {
                using (SqlConnection conn = new SqlConnection(ObtenerCadenaConexion()))
                {
                    using (SqlCommand cmd = new SqlCommand(query, conn))
                    {
                        cmd.Parameters.AddWithValue("@Offset", offset);
                        cmd.Parameters.AddWithValue("@Limite", tamanoPagina);

                        SqlDataAdapter da = new SqlDataAdapter(cmd);
                        da.Fill(dt);
                    }
                }
            }
            catch (Exception ex)
            {
                MessageBox.Show($"Error al consultar la tabla {nombreTabla}: {ex.Message}", "Error SQL", MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
            return dt;
        }

        // Insertar datos masivos usando SqlBulkCopy para TC_Carlo
        public bool GuardarLoteBulk(DataTable datos, string nombreTablaDestino)
        {
            try
            {
                using (SqlConnection conn = new SqlConnection(ObtenerCadenaConexion()))
                {
                    conn.Open();
                    using (SqlBulkCopy bulkCopy = new SqlBulkCopy(conn))
                    {
                        bulkCopy.DestinationTableName = nombreTablaDestino;
                        bulkCopy.BatchSize = 50000;
                        bulkCopy.WriteToServer(datos);
                    }
                }
                return true;
            }
            catch (Exception ex)
            {
                MessageBox.Show($"Error durante la carga masiva: {ex.Message}", "Error BulkCopy", MessageBoxButtons.OK, MessageBoxIcon.Error);
                return false;
            }
        }

        // Mover o registrar un registro eliminado en una tabla de auditoría (Soft Delete)
        public bool EliminarRegistroAuditoria(string nombreTabla, string columnaId, string valorId)
        {
            string query = $"DELETE FROM {nombreTabla} WHERE {columnaId} = @ValorId";

            try
            {
                using (SqlConnection conn = new SqlConnection(ObtenerCadenaConexion()))
                {
                    using (SqlCommand cmd = new SqlCommand(query, conn))
                    {
                        cmd.Parameters.AddWithValue("@ValorId", valorId);
                        conn.Open();
                        cmd.ExecuteNonQuery();
                    }
                }
                return true;
            }
            catch (Exception ex)
            {
                MessageBox.Show($"Error al eliminar el registro: {ex.Message}", "Error de Auditoría", MessageBoxButtons.OK, MessageBoxIcon.Error);
                return false;
            }
        }

        // ==========================================
        // MÉTODOS PARA EL DASHBOARD EN TIEMPO REAL
        // ==========================================

        // Cuenta el total de filas de cualquier tabla
        public long ObtenerTotalRegistros(string nombreTabla)
        {
            try
            {
                using (SqlConnection conn = new SqlConnection(ObtenerCadenaConexion()))
                {
                    conn.Open();
                    // COUNT_BIG permite contar tablas con varios millones de registros.
                    string query = $"SELECT COUNT_BIG(*) FROM {nombreTabla}";
                    using (SqlCommand cmd = new SqlCommand(query, conn))
                    {
                        return Convert.ToInt64(cmd.ExecuteScalar());
                    }
                }
            }
            catch
            {
                return 0; // Si la tabla está vacía o hay error, devuelve 0
            }
        }

        // Cuenta solo los fraudes confirmados (is_fraud = 1)
        public long ObtenerTotalFraudes()
        {
            try
            {
                using (SqlConnection conn = new SqlConnection(ObtenerCadenaConexion()))
                {
                    conn.Open();
                    string query = "SELECT COUNT_BIG(*) FROM fraud_labels WHERE is_fraud = 1";
                    using (SqlCommand cmd = new SqlCommand(query, conn))
                    {
                        return Convert.ToInt64(cmd.ExecuteScalar());
                    }
                }
            }
            catch
            {
                return 0;
            }
        }

        public NuevaTransaccion ObtenerDatosBaseTransaccion(long transactionId)
        {
            using SqlConnection conn = new SqlConnection(ObtenerCadenaConexion());
            conn.Open();
            const string query = @"
                SELECT client_id, card_id, amount, [date], use_chip, mcc
                FROM dbo.transactions_data
                WHERE id = @TransactionId";
            using SqlCommand cmd = new SqlCommand(query, conn);
            cmd.Parameters.Add("@TransactionId", SqlDbType.BigInt).Value = transactionId;
            using SqlDataReader reader = cmd.ExecuteReader();
            if (!reader.Read())
            {
                throw new InvalidOperationException(
                    $"No existe la transacción {transactionId}."
                );
            }

            string amountText = Convert.ToString(reader["amount"], CultureInfo.InvariantCulture)
                ?.Replace("$", string.Empty)
                .Replace(",", string.Empty)
                .Trim() ?? string.Empty;
            if (!decimal.TryParse(
                amountText,
                NumberStyles.Number | NumberStyles.AllowLeadingSign,
                CultureInfo.InvariantCulture,
                out decimal amount
            ))
            {
                throw new InvalidOperationException("El monto de la transacción no es válido.");
            }

            return new NuevaTransaccion
            {
                ClientId = Convert.ToInt32(reader["client_id"]),
                CardId = Convert.ToInt32(reader["card_id"]),
                Amount = amount,
                TransactionDate = Convert.ToDateTime(reader["date"])
                    .ToString("yyyy-MM-ddTHH:mm:ss", CultureInfo.InvariantCulture),
                UseChip = Convert.ToString(reader["use_chip"]) ?? string.Empty,
                Mcc = Convert.ToInt32(reader["mcc"]),
            };
        }

    }

}
