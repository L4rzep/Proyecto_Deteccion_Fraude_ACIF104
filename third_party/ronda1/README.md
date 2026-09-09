# Dependencia exacta del experimento R1

Esta carpeta conserva las fuentes de `imbalanced-learn` 0.15.dev0 y `sklearn_compat` utilizadas en la primera ronda. Se recuperaron del paquete de reproducción del experimento. Su registro de origen identifica [imbalanced-learn 8504e95](https://github.com/scikit-learn-contrib/imbalanced-learn/tree/8504e95f0160f61d1b617ca66f779646d2ee609e) y [sklearn-compat 15b0388](https://github.com/sklearn-compat/sklearn-compat/tree/15b038861332e8a331665bace44e7d8939244991). Las huellas de los archivos incluidos permiten verificar esta copia.

`manifest.json` contiene SHA-256 por archivo del snapshot. Las licencias originales se conservan en `LICENSE` y `LICENSE-sklearn-compat`. El punto de entrada R1 verifica las huellas y carga este directorio localmente, sin instalarlo ni reemplazar paquetes globales. Los experimentos R2, R3, costos e Isolation Forest no necesitan importar el remuestreador.

Esta revisión se usa para reproducir el experimento registrado, con scikit-learn 1.8.0. Sustituirla por otra versión constituye un cambio de entorno que debe documentarse y verificarse.
