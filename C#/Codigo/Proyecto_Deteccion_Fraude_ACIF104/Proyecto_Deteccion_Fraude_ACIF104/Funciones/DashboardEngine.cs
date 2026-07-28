using System;
using System.Drawing;
using System.Drawing.Drawing2D;

namespace Proyecto_Deteccion_Fraude_ACIF104.Funciones
{
    public class DashboardEngine
    {
        // Renderiza en tiempo real el Dashboard visual sobre un PictureBox
        public Bitmap RenderizarDashboard(int ancho, int alto, long totalTransacciones, long totalFraudes, double precision)
        {
            Bitmap bmp = new Bitmap(ancho > 0 ? ancho : 800, alto > 0 ? alto : 400);
            using (Graphics g = Graphics.FromImage(bmp))
            {
                g.SmoothingMode = SmoothingMode.AntiAlias;
                g.Clear(Color.FromArgb(15, 23, 42)); // Fondo azul/gris oscuro

                Font fontTitulo = new Font("Arial", 12, FontStyle.Bold);

                // Tarjetas KPI arriba
                DibujarTarjetaKPI(g, 20, 20, 240, 80, Color.FromArgb(30, 41, 59), Color.FromArgb(56, 189, 248), "TOTAL REGISTROS", totalTransacciones.ToString("N0"), "SQL Server DW");
                DibujarTarjetaKPI(g, 280, 20, 240, 80, Color.FromArgb(30, 41, 59), Color.FromArgb(244, 63, 94), "FRAUDES DETECTADOS", totalFraudes.ToString("N0"), "Modelo XGBoost");
                DibujarTarjetaKPI(g, 540, 20, 240, 80, Color.FromArgb(30, 41, 59), Color.FromArgb(74, 222, 128), "PRECISIÓN IA", $"{precision:F1}%", "Métrica F1-Score");

                // Contenedor del Gráfico de Barras
                int chartX = 20, chartY = 120, chartW = 760, chartH = 240;
                g.FillRectangle(new SolidBrush(Color.FromArgb(30, 41, 59)), chartX, chartY, chartW, chartH);
                g.DrawString("Análisis de Transacciones: Legítimas vs. Fraudulentas", fontTitulo, Brushes.White, chartX + 15, chartY + 15);

                long legitimos = totalTransacciones - totalFraudes;
                long maxVal = Math.Max(legitimos, totalFraudes);
                if (maxVal == 0) maxVal = 1;

                // Barra Transacciones Legítimas
                int altLeg = (int)((double)legitimos / maxVal * 140);
                g.FillRectangle(new SolidBrush(Color.FromArgb(56, 189, 248)), chartX + 180, chartY + 200 - altLeg, 100, altLeg);
                g.DrawString("Legítimas", fontTitulo, Brushes.SkyBlue, chartX + 190, chartY + 210);
                g.DrawString(legitimos.ToString("N0"), fontTitulo, Brushes.White, chartX + 180, chartY + 180 - altLeg);

                // Barra Transacciones Fraudulentas
                int altFraude = (int)((double)totalFraudes / maxVal * 140);
                if (altFraude < 15 && totalFraudes > 0) altFraude = 15;
                g.FillRectangle(new SolidBrush(Color.FromArgb(244, 63, 94)), chartX + 480, chartY + 200 - altFraude, 100, altFraude);
                g.DrawString("Fraudes", fontTitulo, Brushes.Salmon, chartX + 495, chartY + 210);
                g.DrawString(totalFraudes.ToString("N0"), fontTitulo, Brushes.White, chartX + 480, chartY + 180 - altFraude);
            }
            return bmp;
        }

        private void DibujarTarjetaKPI(Graphics g, int x, int y, int w, int h, Color colorFondo, Color colorBorde, string titulo, string valor, string sub)
        {
            g.FillRectangle(new SolidBrush(colorFondo), x, y, w, h);
            g.DrawRectangle(new Pen(colorBorde, 2), x, y, w, h);
            g.DrawString(titulo, new Font("Arial", 8, FontStyle.Bold), new SolidBrush(colorBorde), x + 10, y + 8);
            g.DrawString(valor, new Font("Arial", 15, FontStyle.Bold), Brushes.White, x + 10, y + 26);
            g.DrawString(sub, new Font("Arial", 7, FontStyle.Regular), Brushes.LightGray, x + 10, y + 58);
        }
    }
}