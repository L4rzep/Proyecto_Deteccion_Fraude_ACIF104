using Proyecto_Deteccion_Fraude_ACIF104.Funciones;
using System.Data;
using System.IO;

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
        private TabPage? tabPrediccion;


        public Main()
        {
            InitializeComponent();
            InicializarEstructura();
            Main_TC1.Dock = DockStyle.Fill;
            StartPosition = FormStartPosition.CenterScreen;
            Size = new Size(1200, 800);
            MinimumSize = new Size(1000, 650);
            Shown += Main_Shown;
        }

        private void Main_Shown(object? sender, EventArgs e)
        {
            CargarDashboard();
        }
        private void InicializarEstructura()
        {
            // Hacer que el TabControl ocupe toda la pantalla
            Main_TC1.Dock = DockStyle.Fill;

            // Llenar ComboBoxes de tablas con la lista disponible
            string[] tablas = gestorPlantillas.ObtenerListaTablas();
            Carlo_CB1.DataSource = tablas;
            Explo_CB1.DataSource = tablas;

            // La carga masiva se conserva en el código, pero no forma parte
            // de la interfaz final porque los datos se cargan con el proceso oficial.
            Main_TC1.TabPages.Remove(TC_Carlo);

            // Crear PictureBox para el Dashboard dinámico dentro de TC_Dash
            picDashboard.Dock = DockStyle.Fill;
            picDashboard.SizeMode = PictureBoxSizeMode.StretchImage;
            TC_Dash.Controls.Add(picDashboard);

            // La pestaña de predicción conecta la interfaz con el pipeline final.
            tabPrediccion = new TabPage
            {
                Text = "🤖 Predicción",
                BackColor = System.Drawing.Color.FromArgb(15, 23, 42),
            };
            tabPrediccion.Controls.Add(new PanelPrediccion(pythonEngine, dbManager));
            Main_TC1.TabPages.Add(tabPrediccion);

            // Cargar configuración previa
            Config_TB1.Text = Properties.Settings.Default.CadenaConexion;
            Config_TB2.Text = Properties.Settings.Default.RutaPython;
            Config_LB2.Text = "Cadena de conexión:";
            Config_LB3.Text = "Ejecutable de Python:";
            Config_LB4.Text = "Umbral validado del modelo:";
            Config_LB5.Text = "Porcentaje (solo lectura):";
            Config_NUD1.DecimalPlaces = 2;
            Config_NUD1.Value = 7.22m;
            Config_NUD1.Enabled = false;
            Config_LB6.Text = "Modelo final: Random Forest";
            Config_LB7.Text = "Abrir evaluación:";
            Config_BT2.Text = "Ir a Predicción";
        }

        // Dashboard
        private void Main_TC1_SelectedIndexChanged(object sender, EventArgs e)
        {
            if (Main_TC1.SelectedTab == TC_Dash)
            {
                CargarDashboard();
            }
        }

        private void CargarDashboard()
        {
            long totalTransacciones = dbManager.ObtenerTotalRegistros("fraud_labels");
            long totalFraudes = dbManager.ObtenerTotalFraudes();
            double f1Final = dashEngine.ObtenerF1Final();

            Image? previousImage = picDashboard.Image;
            picDashboard.Image = dashEngine.RenderizarDashboard(
                picDashboard.Width,
                picDashboard.Height,
                totalTransacciones,
                totalFraudes,
                f1Final
            );
            previousImage?.Dispose();
        }

        // Carga y lotes. La pestaña se conserva para trazabilidad, pero está oculta.
        private void Carlo_BT1_Click(object sender, EventArgs e)
        {
            // Botón Exportar Plantilla
            if (Carlo_CB1.SelectedItem is not string tabla) return;
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
                if (Carlo_CB1.SelectedItem is not string tabla) return;
                Carlo_PB1.Value = 50;

                if (dbManager.GuardarLoteBulk(dt, tabla))
                {
                    Carlo_PB1.Value = 100;
                    MessageBox.Show("Datos insertados correctamente en SQL Server.", "Éxito", MessageBoxButtons.OK, MessageBoxIcon.Information);

                    MessageBox.Show(
                        "Los datos quedaron disponibles. Utilice la pestaña Predicción para evaluarlos con el modelo final.",
                        "Carga completada",
                        MessageBoxButtons.OK,
                        MessageBoxIcon.Information
                    );
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
        // Explorador

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
            if (Explo_CB1.SelectedItem is not string tabla) return;
            DataTable dt = dbManager.ObtenerDatosPaginados(tabla, paginaActualExplo, 1000);
            Explo_DGV1.DataSource = dt;
            Explo_LB2.Text = $"Página: {paginaActualExplo}";
        }

        // Configuración
        private void Config_BT1_Click(object sender, EventArgs e)
        {
            // Botón Guardar Configuración
            string cadena = Config_TB1.Text;

            if (!File.Exists(Config_TB2.Text))
            {
                MessageBox.Show(
                    "Seleccione un ejecutable de Python válido.",
                    "Configuración incompleta",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Warning
                );
                return;
            }

            if (dbManager.ProbarConexion(cadena))
            {
                Properties.Settings.Default.CadenaConexion = Config_TB1.Text;
                Properties.Settings.Default.RutaPython = Config_TB2.Text;
                Properties.Settings.Default.Save();

                MessageBox.Show("Configuración guardada y conexión probada con éxito.", "Éxito", MessageBoxButtons.OK, MessageBoxIcon.Information);
            }
        }
        private void Config_BT2_Click(object sender, EventArgs e)
        {
            if (tabPrediccion is null) return;
            Main_TC1.SelectedTab = tabPrediccion;
        }

    }
}
