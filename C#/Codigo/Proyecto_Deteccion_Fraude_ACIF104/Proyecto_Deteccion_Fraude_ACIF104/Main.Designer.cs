namespace Proyecto_Deteccion_Fraude_ACIF104
{
    partial class Main
    {
        /// <summary>
        ///  Required designer variable.
        /// </summary>
        private System.ComponentModel.IContainer components = null;

        /// <summary>
        ///  Clean up any resources being used.
        /// </summary>
        /// <param name="disposing">true if managed resources should be disposed; otherwise, false.</param>
        protected override void Dispose(bool disposing)
        {
            if (disposing && (components != null))
            {
                components.Dispose();
            }
            base.Dispose(disposing);
        }

        #region Windows Form Designer generated code

        /// <summary>
        ///  Required method for Designer support - do not modify
        ///  the contents of this method with the code editor.
        /// </summary>
        private void InitializeComponent()
        {
            System.ComponentModel.ComponentResourceManager resources = new System.ComponentModel.ComponentResourceManager(typeof(Main));
            TC_Config = new TabPage();
            Config_BT2 = new Button();
            Config_LB7 = new Label();
            Config_LB6 = new Label();
            Config_NUD1 = new NumericUpDown();
            Config_TB2 = new TextBox();
            Config_TB1 = new TextBox();
            Config_BT1 = new Button();
            Config_LB5 = new Label();
            Config_LB4 = new Label();
            Config_LB3 = new Label();
            Config_LB1 = new Label();
            Config_LB2 = new Label();
            TC_Explo = new TabPage();
            Explo_CB1 = new ComboBox();
            Explo_BT2 = new Button();
            Explo_BT1 = new Button();
            Explo_DGV1 = new DataGridView();
            Explo_LB2 = new Label();
            Explo_LB1 = new Label();
            TC_Carlo = new TabPage();
            Carlo_CB1 = new ComboBox();
            Carlo_BT2 = new Button();
            Carlo_BT1 = new Button();
            Carlo_BT4 = new Button();
            Carlo_BT3 = new Button();
            Carlo_PB1 = new ProgressBar();
            Carlo_DGV1 = new DataGridView();
            Carlo_LB4 = new Label();
            Carlo_LB1 = new Label();
            Carlo_LB3 = new Label();
            Carlo_LB2 = new Label();
            TC_Dash = new TabPage();
            Main_TC1 = new TabControl();
            TC_Config.SuspendLayout();
            ((System.ComponentModel.ISupportInitialize)Config_NUD1).BeginInit();
            TC_Explo.SuspendLayout();
            ((System.ComponentModel.ISupportInitialize)Explo_DGV1).BeginInit();
            TC_Carlo.SuspendLayout();
            ((System.ComponentModel.ISupportInitialize)Carlo_DGV1).BeginInit();
            Main_TC1.SuspendLayout();
            SuspendLayout();
            // 
            // TC_Config
            // 
            TC_Config.BackgroundImage = Properties.Resources.Fondo_azul1_100;
            TC_Config.BackgroundImageLayout = ImageLayout.Stretch;
            TC_Config.Controls.Add(Config_BT2);
            TC_Config.Controls.Add(Config_LB7);
            TC_Config.Controls.Add(Config_LB6);
            TC_Config.Controls.Add(Config_NUD1);
            TC_Config.Controls.Add(Config_TB2);
            TC_Config.Controls.Add(Config_TB1);
            TC_Config.Controls.Add(Config_BT1);
            TC_Config.Controls.Add(Config_LB5);
            TC_Config.Controls.Add(Config_LB4);
            TC_Config.Controls.Add(Config_LB3);
            TC_Config.Controls.Add(Config_LB1);
            TC_Config.Controls.Add(Config_LB2);
            TC_Config.Location = new Point(4, 24);
            TC_Config.Name = "TC_Config";
            TC_Config.Padding = new Padding(3);
            TC_Config.Size = new Size(1068, 498);
            TC_Config.TabIndex = 4;
            TC_Config.Text = "⚙️ Configuración";
            TC_Config.UseVisualStyleBackColor = true;
            // 
            // Config_BT2
            // 
            Config_BT2.Location = new Point(151, 235);
            Config_BT2.Name = "Config_BT2";
            Config_BT2.Size = new Size(75, 23);
            Config_BT2.TabIndex = 15;
            Config_BT2.Text = "Activar";
            Config_BT2.UseVisualStyleBackColor = true;
            Config_BT2.Click += Config_BT2_Click;
            // 
            // Config_LB7
            // 
            Config_LB7.AutoSize = true;
            Config_LB7.ForeColor = SystemColors.ButtonFace;
            Config_LB7.Location = new Point(51, 243);
            Config_LB7.Name = "Config_LB7";
            Config_LB7.Size = new Size(94, 15);
            Config_LB7.TabIndex = 14;
            Config_LB7.Text = "Activar a FINAN:";
            // 
            // Config_LB6
            // 
            Config_LB6.AutoSize = true;
            Config_LB6.Font = new Font("Segoe UI", 12F);
            Config_LB6.ForeColor = SystemColors.ButtonFace;
            Config_LB6.Location = new Point(6, 204);
            Config_LB6.Name = "Config_LB6";
            Config_LB6.Size = new Size(137, 21);
            Config_LB6.TabIndex = 13;
            Config_LB6.Text = "Accion FINAN (IA):";
            // 
            // Config_NUD1
            // 
            Config_NUD1.Location = new Point(209, 153);
            Config_NUD1.Name = "Config_NUD1";
            Config_NUD1.Size = new Size(54, 23);
            Config_NUD1.TabIndex = 12;
            // 
            // Config_TB2
            // 
            Config_TB2.Location = new Point(209, 89);
            Config_TB2.Name = "Config_TB2";
            Config_TB2.Size = new Size(348, 23);
            Config_TB2.TabIndex = 11;
            // 
            // Config_TB1
            // 
            Config_TB1.Location = new Point(209, 53);
            Config_TB1.Name = "Config_TB1";
            Config_TB1.Size = new Size(348, 23);
            Config_TB1.TabIndex = 10;
            // 
            // Config_BT1
            // 
            Config_BT1.Location = new Point(6, 457);
            Config_BT1.Name = "Config_BT1";
            Config_BT1.Size = new Size(75, 23);
            Config_BT1.TabIndex = 9;
            Config_BT1.Text = "Guardar";
            Config_BT1.UseVisualStyleBackColor = true;
            // 
            // Config_LB5
            // 
            Config_LB5.AutoSize = true;
            Config_LB5.ForeColor = SystemColors.ButtonFace;
            Config_LB5.Location = new Point(51, 161);
            Config_LB5.Name = "Config_LB5";
            Config_LB5.Size = new Size(73, 15);
            Config_LB5.TabIndex = 8;
            Config_LB5.Text = "Sensibilidad:";
            // 
            // Config_LB4
            // 
            Config_LB4.AutoSize = true;
            Config_LB4.Font = new Font("Segoe UI", 12F);
            Config_LB4.ForeColor = SystemColors.ButtonFace;
            Config_LB4.Location = new Point(6, 130);
            Config_LB4.Name = "Config_LB4";
            Config_LB4.Size = new Size(138, 21);
            Config_LB4.TabIndex = 7;
            Config_LB4.Text = "Umbral de Fraude:";
            // 
            // Config_LB3
            // 
            Config_LB3.AutoSize = true;
            Config_LB3.ForeColor = SystemColors.ButtonFace;
            Config_LB3.Location = new Point(51, 97);
            Config_LB3.Name = "Config_LB3";
            Config_LB3.Size = new Size(146, 15);
            Config_LB3.TabIndex = 4;
            Config_LB3.Text = "Nombre de Base de Datos:";
            // 
            // Config_LB1
            // 
            Config_LB1.AutoSize = true;
            Config_LB1.Font = new Font("Segoe UI", 12F);
            Config_LB1.ForeColor = SystemColors.ButtonFace;
            Config_LB1.Location = new Point(6, 28);
            Config_LB1.Name = "Config_LB1";
            Config_LB1.Size = new Size(207, 21);
            Config_LB1.TabIndex = 3;
            Config_LB1.Text = "Conexión a la Base de Datos:";
            // 
            // Config_LB2
            // 
            Config_LB2.AutoSize = true;
            Config_LB2.ForeColor = SystemColors.ButtonFace;
            Config_LB2.Location = new Point(51, 61);
            Config_LB2.Name = "Config_LB2";
            Config_LB2.Size = new Size(77, 15);
            Config_LB2.TabIndex = 1;
            Config_LB2.Text = "Servidor SQL:";
            // 
            // TC_Explo
            // 
            TC_Explo.BackgroundImage = Properties.Resources.Fondo_azul1_100;
            TC_Explo.BackgroundImageLayout = ImageLayout.Stretch;
            TC_Explo.Controls.Add(Explo_CB1);
            TC_Explo.Controls.Add(Explo_BT2);
            TC_Explo.Controls.Add(Explo_BT1);
            TC_Explo.Controls.Add(Explo_DGV1);
            TC_Explo.Controls.Add(Explo_LB2);
            TC_Explo.Controls.Add(Explo_LB1);
            TC_Explo.Location = new Point(4, 24);
            TC_Explo.Name = "TC_Explo";
            TC_Explo.Padding = new Padding(3);
            TC_Explo.Size = new Size(1068, 498);
            TC_Explo.TabIndex = 2;
            TC_Explo.Text = "🔍 Explorador";
            TC_Explo.UseVisualStyleBackColor = true;
            // 
            // Explo_CB1
            // 
            Explo_CB1.FormattingEnabled = true;
            Explo_CB1.Location = new Point(121, 13);
            Explo_CB1.Name = "Explo_CB1";
            Explo_CB1.Size = new Size(154, 23);
            Explo_CB1.TabIndex = 6;
            Explo_CB1.SelectedIndexChanged += Explo_CB1_SelectedIndexChanged;
            // 
            // Explo_BT2
            // 
            Explo_BT2.Location = new Point(87, 467);
            Explo_BT2.Name = "Explo_BT2";
            Explo_BT2.Size = new Size(75, 23);
            Explo_BT2.TabIndex = 5;
            Explo_BT2.Text = "Siguiente";
            Explo_BT2.UseVisualStyleBackColor = true;
            Explo_BT2.Click += Explo_BT2_Click;
            // 
            // Explo_BT1
            // 
            Explo_BT1.Location = new Point(6, 467);
            Explo_BT1.Name = "Explo_BT1";
            Explo_BT1.Size = new Size(75, 23);
            Explo_BT1.TabIndex = 4;
            Explo_BT1.Text = "Anterior";
            Explo_BT1.UseVisualStyleBackColor = true;
            Explo_BT1.Click += Explo_BT1_Click;
            // 
            // Explo_DGV1
            // 
            Explo_DGV1.ColumnHeadersHeightSizeMode = DataGridViewColumnHeadersHeightSizeMode.AutoSize;
            Explo_DGV1.Location = new Point(6, 47);
            Explo_DGV1.Name = "Explo_DGV1";
            Explo_DGV1.Size = new Size(856, 414);
            Explo_DGV1.TabIndex = 3;
            // 
            // Explo_LB2
            // 
            Explo_LB2.AutoSize = true;
            Explo_LB2.ForeColor = SystemColors.ButtonFace;
            Explo_LB2.Location = new Point(809, 464);
            Explo_LB2.Name = "Explo_LB2";
            Explo_LB2.Size = new Size(53, 15);
            Explo_LB2.TabIndex = 2;
            Explo_LB2.Text = "Pagina X";
            // 
            // Explo_LB1
            // 
            Explo_LB1.AutoSize = true;
            Explo_LB1.ForeColor = SystemColors.ButtonFace;
            Explo_LB1.Location = new Point(6, 21);
            Explo_LB1.Name = "Explo_LB1";
            Explo_LB1.Size = new Size(109, 15);
            Explo_LB1.TabIndex = 1;
            Explo_LB1.Text = "Seleccione la Tabla:";
            // 
            // TC_Carlo
            // 
            TC_Carlo.BackgroundImage = Properties.Resources.Fondo_azul1_100;
            TC_Carlo.BackgroundImageLayout = ImageLayout.Stretch;
            TC_Carlo.Controls.Add(Carlo_CB1);
            TC_Carlo.Controls.Add(Carlo_BT2);
            TC_Carlo.Controls.Add(Carlo_BT1);
            TC_Carlo.Controls.Add(Carlo_BT4);
            TC_Carlo.Controls.Add(Carlo_BT3);
            TC_Carlo.Controls.Add(Carlo_PB1);
            TC_Carlo.Controls.Add(Carlo_DGV1);
            TC_Carlo.Controls.Add(Carlo_LB4);
            TC_Carlo.Controls.Add(Carlo_LB1);
            TC_Carlo.Controls.Add(Carlo_LB3);
            TC_Carlo.Controls.Add(Carlo_LB2);
            TC_Carlo.Location = new Point(4, 24);
            TC_Carlo.Name = "TC_Carlo";
            TC_Carlo.Padding = new Padding(3);
            TC_Carlo.Size = new Size(1068, 498);
            TC_Carlo.TabIndex = 1;
            TC_Carlo.Text = "📥 Carga & Lotes";
            TC_Carlo.UseVisualStyleBackColor = true;
            // 
            // Carlo_CB1
            // 
            Carlo_CB1.FormattingEnabled = true;
            Carlo_CB1.Location = new Point(128, 24);
            Carlo_CB1.Name = "Carlo_CB1";
            Carlo_CB1.Size = new Size(172, 23);
            Carlo_CB1.TabIndex = 12;
            // 
            // Carlo_BT2
            // 
            Carlo_BT2.Location = new Point(141, 103);
            Carlo_BT2.Name = "Carlo_BT2";
            Carlo_BT2.Size = new Size(75, 23);
            Carlo_BT2.TabIndex = 11;
            Carlo_BT2.Text = "Importar";
            Carlo_BT2.UseVisualStyleBackColor = true;
            Carlo_BT2.Click += Carlo_BT2_Click;
            // 
            // Carlo_BT1
            // 
            Carlo_BT1.Location = new Point(141, 69);
            Carlo_BT1.Name = "Carlo_BT1";
            Carlo_BT1.Size = new Size(75, 23);
            Carlo_BT1.TabIndex = 10;
            Carlo_BT1.Text = "Exportar";
            Carlo_BT1.UseVisualStyleBackColor = true;
            Carlo_BT1.Click += Carlo_BT1_Click;
            // 
            // Carlo_BT4
            // 
            Carlo_BT4.Location = new Point(883, 214);
            Carlo_BT4.Name = "Carlo_BT4";
            Carlo_BT4.Size = new Size(75, 23);
            Carlo_BT4.TabIndex = 9;
            Carlo_BT4.Text = "Cancelar";
            Carlo_BT4.UseVisualStyleBackColor = true;
            Carlo_BT4.Click += Carlo_BT4_Click;
            // 
            // Carlo_BT3
            // 
            Carlo_BT3.Location = new Point(883, 185);
            Carlo_BT3.Name = "Carlo_BT3";
            Carlo_BT3.Size = new Size(75, 23);
            Carlo_BT3.TabIndex = 8;
            Carlo_BT3.Text = "Guardar";
            Carlo_BT3.UseVisualStyleBackColor = true;
            Carlo_BT3.Click += Carlo_BT3_Click;
            // 
            // Carlo_PB1
            // 
            Carlo_PB1.Location = new Point(26, 156);
            Carlo_PB1.Name = "Carlo_PB1";
            Carlo_PB1.Size = new Size(851, 23);
            Carlo_PB1.TabIndex = 6;
            // 
            // Carlo_DGV1
            // 
            Carlo_DGV1.ColumnHeadersHeightSizeMode = DataGridViewColumnHeadersHeightSizeMode.AutoSize;
            Carlo_DGV1.Location = new Point(26, 185);
            Carlo_DGV1.Name = "Carlo_DGV1";
            Carlo_DGV1.Size = new Size(851, 307);
            Carlo_DGV1.TabIndex = 5;
            // 
            // Carlo_LB4
            // 
            Carlo_LB4.AutoSize = true;
            Carlo_LB4.ForeColor = SystemColors.ButtonFace;
            Carlo_LB4.Location = new Point(350, 131);
            Carlo_LB4.Name = "Carlo_LB4";
            Carlo_LB4.Size = new Size(118, 15);
            Carlo_LB4.TabIndex = 4;
            Carlo_LB4.Text = "Progreso del Importe";
            // 
            // Carlo_LB1
            // 
            Carlo_LB1.AutoSize = true;
            Carlo_LB1.Font = new Font("Segoe UI", 12F);
            Carlo_LB1.ForeColor = SystemColors.ButtonFace;
            Carlo_LB1.Location = new Point(26, 26);
            Carlo_LB1.Name = "Carlo_LB1";
            Carlo_LB1.Size = new Size(96, 21);
            Carlo_LB1.TabIndex = 3;
            Carlo_LB1.Text = "Elija la Tabla:";
            // 
            // Carlo_LB3
            // 
            Carlo_LB3.AutoSize = true;
            Carlo_LB3.ForeColor = SystemColors.ButtonFace;
            Carlo_LB3.Location = new Point(26, 111);
            Carlo_LB3.Name = "Carlo_LB3";
            Carlo_LB3.Size = new Size(101, 15);
            Carlo_LB3.TabIndex = 2;
            Carlo_LB3.Text = "Importar Plantilla:";
            // 
            // Carlo_LB2
            // 
            Carlo_LB2.AutoSize = true;
            Carlo_LB2.ForeColor = SystemColors.ButtonFace;
            Carlo_LB2.Location = new Point(26, 77);
            Carlo_LB2.Name = "Carlo_LB2";
            Carlo_LB2.Size = new Size(98, 15);
            Carlo_LB2.TabIndex = 1;
            Carlo_LB2.Text = "Exportar Plantilla:";
            // 
            // TC_Dash
            // 
            TC_Dash.BackgroundImage = Properties.Resources.Fondo_azul1_100;
            TC_Dash.BackgroundImageLayout = ImageLayout.Stretch;
            TC_Dash.Location = new Point(4, 24);
            TC_Dash.Name = "TC_Dash";
            TC_Dash.Padding = new Padding(3);
            TC_Dash.Size = new Size(1068, 498);
            TC_Dash.TabIndex = 0;
            TC_Dash.Text = "📊 Dashboard";
            TC_Dash.UseVisualStyleBackColor = true;
            // 
            // Main_TC1
            // 
            Main_TC1.Controls.Add(TC_Dash);
            Main_TC1.Controls.Add(TC_Carlo);
            Main_TC1.Controls.Add(TC_Explo);
            Main_TC1.Controls.Add(TC_Config);
            Main_TC1.Location = new Point(12, 12);
            Main_TC1.Multiline = true;
            Main_TC1.Name = "Main_TC1";
            Main_TC1.SelectedIndex = 0;
            Main_TC1.Size = new Size(1076, 526);
            Main_TC1.SizeMode = TabSizeMode.FillToRight;
            Main_TC1.TabIndex = 0;
            Main_TC1.SelectedIndexChanged += Main_TC1_SelectedIndexChanged;
            // 
            // Main
            // 
            AutoScaleDimensions = new SizeF(7F, 15F);
            AutoScaleMode = AutoScaleMode.Font;
            BackColor = SystemColors.ButtonFace;
            BackgroundImage = Properties.Resources.Fondo_azul1_100;
            BackgroundImageLayout = ImageLayout.Stretch;
            ClientSize = new Size(1095, 542);
            Controls.Add(Main_TC1);
            Icon = (Icon)resources.GetObject("$this.Icon");
            Name = "Main";
            Text = "Proyecto Deteccion Fraude ACIF104";
            TC_Config.ResumeLayout(false);
            TC_Config.PerformLayout();
            ((System.ComponentModel.ISupportInitialize)Config_NUD1).EndInit();
            TC_Explo.ResumeLayout(false);
            TC_Explo.PerformLayout();
            ((System.ComponentModel.ISupportInitialize)Explo_DGV1).EndInit();
            TC_Carlo.ResumeLayout(false);
            TC_Carlo.PerformLayout();
            ((System.ComponentModel.ISupportInitialize)Carlo_DGV1).EndInit();
            Main_TC1.ResumeLayout(false);
            ResumeLayout(false);
        }

        #endregion

        private TabPage TC_Config;
        private Button Config_BT1;
        private Label Config_LB5;
        private Label Config_LB4;
        private Label Config_LB3;
        private Label Config_LB1;
        private Label Config_LB2;
        private TabPage TC_Explo;
        private ComboBox Explo_CB1;
        private Button Explo_BT2;
        private Button Explo_BT1;
        private DataGridView Explo_DGV1;
        private Label Explo_LB2;
        private Label Explo_LB1;
        private TabPage TC_Carlo;
        private ComboBox Carlo_CB1;
        private Button Carlo_BT2;
        private Button Carlo_BT1;
        private Button Carlo_BT4;
        private Button Carlo_BT3;
        private ProgressBar Carlo_PB1;
        private DataGridView Carlo_DGV1;
        private Label Carlo_LB4;
        private Label Carlo_LB1;
        private Label Carlo_LB3;
        private Label Carlo_LB2;
        private TabPage TC_Dash;
        private TabControl Main_TC1;
        private NumericUpDown Config_NUD1;
        private TextBox Config_TB2;
        private TextBox Config_TB1;
        private Label Config_LB7;
        private Label Config_LB6;
        private Button Config_BT2;
    }
}
