# Estructura e identidad de una carta

Referencia del usuario: [diagrama de Kuriboh](user-reference.jpg). La imagen es una guía de una carta clásica; no define coordenadas universales para todos los diseños.

La jerarquía del registro es **identidad → nombres por idioma → artes → observaciones de impresiones**. Cada observación conserva fuente, identificador del registro original y evidencia. Dos fuentes pueden describir la misma impresión: contar filas no equivale a contar impresiones físicas distintas.

| Elemento | Significado y tratamiento |
|---|---|
| Nombre | Nombre localizado, con posibles revisiones. Conservar variantes como observaciones, no usarlo como clave universal. |
| Passcode | Normalmente ocho dígitos abajo a la izquierda. Texto, con ceros iniciales. Usar solamente `passwords` de YGOJSON como evidencia inicial de passcode. Puede faltar o existir más de uno asociado a una identidad. |
| Set code | Identifica el producto y número de carta, frecuentemente con región/idioma. Conservar texto literal, incluso códigos antiguos sin idioma. No es único por rareza o edición. |
| CID Neuron | Identificador de la ficha oficial, diferente del passcode; no necesariamente aparece impreso. |
| ID del juego / imagen | Permite localizar recursos, no demuestra un passcode. Ejemplo: 89631140 es un ID de imagen de Blue-Eyes en la fuente; 89631139 es su passcode de identidad. |
| Arte | Ilustración alternativa con ID propio. No confundir un cambio de brillo, borde, encuadre o rareza con un arte distinto. |
| Rareza / acabado | Propiedad de impresión. Guardar el valor original de cada fuente; sus vocabularios no son necesariamente equivalentes. |
| Edición | Primera, ilimitada, limitada, etc. Sólo asignarla a una impresión con evidencia directa; las ediciones disponibles del producto se guardan aparte como candidatas. |
| Atributo y nivel/rango | Atributo junto al nombre y estrellas debajo. No aplican igual a todos los tipos. |
| Tipo y texto | Tipo de monstruo y habilidades, o clase de Magia/Trampa; texto localizado y sujeto a erratas. |
| ATK/DEF o LINK | Estadísticas de monstruos; Link no tiene DEF. No sustituir `?` por cero. |
| Copyright / sello | Señales auxiliares de diseño y edición, no identificadores de identidad. |

El `setcode` numérico de las tablas `datas` del simulador no es el código impreso del producto. La tabla `pack.db` sí contiene códigos como `LOB-001`, pero sólo aporta una fila por ID del juego: no contiene todo el historial.

## Zonas y reconocimiento

Las zonas aproximadas están en [anatomy.json](anatomy.json), normalizadas sobre la carta completa después de corregir perspectiva. Son propuestas manuales para iniciar anotación; no son un detector entrenado ni límites precisos.

1. Detectar las cuatro esquinas y rectificar con homografía. La perspectiva requiere una transformación proyectiva, no sólo lineal.
2. Resolver orientación 0/90/180/270 antes de leer. Hacer representaciones resistentes a rotación sin borrar la orientación necesaria para OCR.
3. Identificar el tipo de plantilla: clásica, Péndulo, Link, Magia/Trampa, Skill, Token y otros. Calibrar zonas por plantilla; no recortar todas con el mismo rectángulo.
4. Comparar ilustración y candidatos de identidad; combinar con OCR de passcode y nombre localizado. Conservar resultado desconocido cuando falte evidencia.
5. Resolver impresión con OCR del set code más idioma, rareza/edición y comparación visual. El set code por sí solo puede devolver varias posibilidades válidas.
6. Tratar sombras, reflejos y foil como variaciones de captura/acabado: corrección fotométrica y entrenamiento con ejemplos reales. No convertir una imagen artificial en prueba de una impresión real.

Para entrenamiento, separar por copia física/sesión y agrupar variantes de identidad para evitar fugas entre entrenamiento y evaluación. Medir precisión por idioma, arte y acabado, además de rechazo de cartas desconocidas.
