using Proyecto_Deteccion_Fraude_ACIF104.Funciones;
using System.Data;
using System.Threading.Tasks;
using System.Text;

namespace Proyecto_Deteccion_Fraude_ACIF104
{
    public partial class Main : Form
    {
        // Instancia de las clases del namespace Funciones
        private DatabaseManager dbManager = new DatabaseManager();
        private DashboardEngine dashEngine = new DashboardEngine();
        private GestorPlantillas gestorPlantillas = new GestorPlantillas();
        private PythonEngine pythonEngine = new PythonEngine();

        private int paginaActualExplo = 1;
        private PictureBox picDashboard = new PictureBox();


        public Main()
        {
            InitializeComponent();
            InicializarEstructura();
            Main_TC1.Dock = DockStyle.Fill;
        }
        private void InicializarEstructura()
        {
            // Hacer que el TabControl ocupe toda la pantalla
            Main_TC1.Dock = DockStyle.Fill;

            // Llenar ComboBoxes de tablas con la lista disponible
            string[] tablas = gestorPlantillas.ObtenerListaTablas();
            Carlo_CB1.DataSource = tablas;
            Explo_CB1.DataSource = tablas;

            // Crear PictureBox para el Dashboard dinámico dentro de TC_Dash
            picDashboard.Dock = DockStyle.Fill;
            picDashboard.SizeMode = PictureBoxSizeMode.StretchImage;
            TC_Dash.Controls.Add(picDashboard);

            // Cargar configuración previa
            Config_TB1.Text = Properties.Settings.Default.CadenaConexion;
            Config_TB2.Text = Properties.Settings.Default.RutaPython;
            if (Properties.Settings.Default.UmbralFraude > 0)
                Config_NUD1.Value = Properties.Settings.Default.UmbralFraude;
        }

        // ==========================================
        // 📊 TAB 1: DASHBOARD (AHORA 100% REAL)
        // ==========================================
        private void Main_TC1_SelectedIndexChanged(object sender, EventArgs e)
        {
            if (Main_TC1.SelectedTab == TC_Dash)
            {
                // 1. Ir a SQL Server y contar los datos REALES
                long totalTransacciones = dbManager.ObtenerTotalRegistros("transactions_data");
                long totalFraudes = dbManager.ObtenerTotalFraudes();

                // 2. Calcular la precisión de forma dinámica (Evitar división por cero)
                double precision = 0;
                if (totalTransacciones > 0)
                {
                    long transaccionesLegitimas = totalTransacciones - totalFraudes;
                    precision = ((double)transaccionesLegitimas / totalTransacciones) * 100;
                }

                // 3. Generar gráfico dinámico con la data real
                picDashboard.Image = dashEngine.RenderizarDashboard(
                    picDashboard.Width, picDashboard.Height,
                    totalTransacciones, totalFraudes, precision
                );
            }
        }

        // ==========================================
        // 📥 TAB 2: CARGA & LOTES (Carlo_)
        // ==========================================
        private void Carlo_BT1_Click(object sender, EventArgs e)
        {
            // Botón Exportar Plantilla
            string tabla = Carlo_CB1.SelectedItem.ToString();
            SaveFileDialog sfd = new SaveFileDialog { Filter = "CSV|*.csv", FileName = $"Plantilla_{tabla}.csv" };
            if (sfd.ShowDialog() == DialogResult.OK)
            {
                gestorPlantillas.ExportarPlantilla(tabla, sfd.FileName);
                MessageBox.Show("Plantilla exportada correctamente.", "Éxito", MessageBoxButtons.OK, MessageBoxIcon.Information);
            }
        }

        private void Carlo_BT2_Click(object sender, EventArgs e)
        {
            // Botón Importar Plantilla
            OpenFileDialog ofd = new OpenFileDialog { Filter = "CSV|*.csv" };
            if (ofd.ShowDialog() == DialogResult.OK)
            {
                DataTable dt = gestorPlantillas.CargarCSV(ofd.FileName);
                Carlo_DGV1.DataSource = dt;
                Carlo_LB4.Text = $"Registros cargados: {dt.Rows.Count}";
            }
        }

        private void Carlo_BT3_Click(object sender, EventArgs e)
        {
            // Botón Guardar en SQL Server
            if (Carlo_DGV1.DataSource is DataTable dt && dt.Rows.Count > 0)
            {
                string tabla = Carlo_CB1.SelectedItem.ToString();
                Carlo_PB1.Value = 50;

                if (dbManager.GuardarLoteBulk(dt, tabla))
                {
                    Carlo_PB1.Value = 100;
                    MessageBox.Show("Datos insertados correctamente en SQL Server.", "Éxito", MessageBoxButtons.OK, MessageBoxIcon.Information);

                    // Ejecutar inferencia de Python automáticamente
                    string resultado = pythonEngine.EjecutarModeloInferencia(1, dt.Rows.Count);
                    MessageBox.Show($"Respuesta del Motor IA:\n{resultado}", "Log de Python", MessageBoxButtons.OK, MessageBoxIcon.Information);
                }
                Carlo_PB1.Value = 0;
            }
        }

        private void Carlo_BT4_Click(object sender, EventArgs e)
        {
            // Botón Cancelar
            Carlo_DGV1.DataSource = null;
            Carlo_LB4.Text = "Carga cancelada.";
            Carlo_PB1.Value = 0;
        }
        // ==========================================
        // 🔍 TAB 3: EXPLORADOR (Explo_)
        // ==========================================

        private void Explo_CB1_SelectedIndexChanged(object sender, EventArgs e)
        {
            paginaActualExplo = 1;
            CargarDatosExplorador();
        }

        private void Explo_BT1_Click(object sender, EventArgs e)
        {
            // Botón Anterior
            if (paginaActualExplo > 1)
            {
                paginaActualExplo--;
                CargarDatosExplorador();
            }
        }

        private void Explo_BT2_Click(object sender, EventArgs e)
        {
            // Botón Siguiente
            paginaActualExplo++;
            CargarDatosExplorador();
        }

        private void CargarDatosExplorador()
        {
            if (Explo_CB1.SelectedItem == null) return;

            string tabla = Explo_CB1.SelectedItem.ToString();
            DataTable dt = dbManager.ObtenerDatosPaginados(tabla, paginaActualExplo, 1000);
            Explo_DGV1.DataSource = dt;
            Explo_LB2.Text = $"Página: {paginaActualExplo}";
        }

        // ==========================================
        // ⚙️ TAB 4: CONFIGURACIÓN (Config_)
        // ==========================================
        private void Config_BT1_Click(object sender, EventArgs e)
        {
            // Botón Guardar Configuración
            string cadena = Config_TB1.Text;

            if (dbManager.ProbarConexion(cadena))
            {
                Properties.Settings.Default.CadenaConexion = Config_TB1.Text;
                Properties.Settings.Default.RutaPython = Config_TB2.Text;
                Properties.Settings.Default.UmbralFraude = Config_NUD1.Value ;
                Properties.Settings.Default.Save();

                MessageBox.Show("Configuración guardada y conexión probada con éxito.", "Éxito", MessageBoxButtons.OK, MessageBoxIcon.Information);
            }
        }
        // Fíjate que ahora dice "async void"
        private async void Config_BT2_Click(object sender, EventArgs e)
        {
            int ultimoProcesado = dbManager.ObtenerUltimoIDProcesado();
            int totalTransacciones = dbManager.ObtenerMaximoIDTransacciones();

            if (ultimoProcesado >= totalTransacciones)
            {
                MessageBox.Show("FINAN ya analizó todas las transacciones. No hay datos nuevos.", "Sistema Actualizado", MessageBoxButtons.OK, MessageBoxIcon.Information);
                return;
            }

            int tamanoLote = 1000000; // Paquetes de 1 Millón de registros
            int idInicio = ultimoProcesado + 1;

            // =========================================================
            // 🎨 CREACIÓN DEL RECUADRO DE ESPERA (Cargando...)
            // =========================================================
            Form formEspera = new Form
            {
                Text = "IA FINAN Trabajando...",
                Size = new System.Drawing.Size(350, 150),
                StartPosition = FormStartPosition.CenterScreen,
                FormBorderStyle = FormBorderStyle.FixedDialog,
                ControlBox = false, // Quita la 'X' para que no lo puedan cerrar a la fuerza
                BackColor = System.Drawing.Color.FromArgb(15, 23, 42) // Fondo oscuro elegante
            };

            Label lblEstado = new Label
            {
                Text = $"Iniciando motor de IA...\nTransacciones pendientes: {totalTransacciones - ultimoProcesado:N0}",
                AutoSize = false,
                TextAlign = System.Drawing.ContentAlignment.MiddleCenter,
                Dock = DockStyle.Fill,
                Font = new System.Drawing.Font("Arial", 11, System.Drawing.FontStyle.Bold),
                ForeColor = System.Drawing.Color.White
            };
            formEspera.Controls.Add(lblEstado);

            // Deshabilitar el botón para que no hagan doble clic
            Config_BT2.Enabled = false;

            // Mostrar el recuadro sin congelar la app
            formEspera.Show(this);

            // =========================================================
            // ⚙️ BUCLE MÁGICO EN SEGUNDO PLANO (Task.Run)
            // =========================================================
            await Task.Run(() =>
            {
                StringBuilder logFinal = new StringBuilder(); // Para guardar todos los reportes

                while (idInicio <= totalTransacciones)
                {
                    int idFin = idInicio + tamanoLote - 1;

                    if (idFin > totalTransacciones)
                    {
                        idFin = totalTransacciones;
                    }

                    // Actualizar el recuadro de espera en tiempo real (Invoke es necesario al usar hilos secundarios)
                    lblEstado.Invoke((MethodInvoker)delegate {
                        lblEstado.Text = $"Analizando lote de datos:\n{idInicio:N0} al {idFin:N0}\n\n¡Por favor, no cierre el sistema!";
                    });

                    // Llama a Python silenciosamente
                    string log = pythonEngine.EjecutarModeloInferencia(idInicio, idFin);
                    logFinal.AppendLine($"Lote {idInicio:N0}-{idFin:N0} completado.");

                    idInicio = idFin + 1;
                }
            });

            // =========================================================
            // ✅ FINALIZACIÓN
            // =========================================================
            // Cerrar el recuadro de espera y rehabilitar el botón
            formEspera.Close();
            Config_BT2.Enabled = true;

            // Mostrar mensaje final de éxito
            MessageBox.Show("¡Todos los datos han sido analizados por FINAN y guardados en SQL exitosamente!", "Proceso Completado", MessageBoxButtons.OK, MessageBoxIcon.Information);
        }

    }
}
