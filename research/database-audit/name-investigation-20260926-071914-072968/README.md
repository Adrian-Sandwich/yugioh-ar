# Investigación de los 104 huecos de nombres

Se consultaron las 67 páginas de Yugipedia referenciadas por las identidades
locales, usando sus IDs de página. Se guardaron respuestas de API, revisiones,
URLs y hashes SHA256. Resultado para los 104 pares carta–idioma:

- 101 campos de nombre localizado vacíos.
- Tres campos ausentes o sin valor único.
- Ningún nombre recuperado con evidencia suficiente para importarlo.

No es un fallo de importación demostrado: las fuentes consultadas tampoco
aportan el texto que falta. No se generaron traducciones ni se copiaron nombres
ingleses como si fueran nombres impresos en otro idioma. Las ausencias no
demuestran que una edición física no exista.

Los seis CIDs positivos de cartas no Skill se consultaron directamente en
Neuron en portugués. Las respuestas no contienen una ficha que acepte el parser
actual. Los HTML quedaron guardados para distinguir un fallo del parser de una
ficha realmente no disponible en una revisión posterior.

Diez pares de tipo Skill tienen un `dbID` negativo en la fuente. Se marcaron
`nonpositive_identifier_needs_review`: no se asume que sean CIDs válidos de
Neuron ni se convierten al valor absoluto. Los primeros intentos con esos
valores tampoco recuperaron ficha; sus HTML se conservan, pero el investigador
actual omite nuevas consultas de identificadores no positivos.

## Archivos

- `results.json`: cada caso, set code, fuente original, campos consultados,
  revisión de Yugipedia y resultado de Neuron.
- `yugipedia-*.json`: respuestas completas de la API (67 páginas en cuatro lotes).
- `neuron-*.html`: respuestas de las consultas oficiales.

Ejemplo comprobado: la revisión obtenida de
[Machine Angel Ascension](https://yugipedia.com/wiki/Machine_Angel_Ascension)
tiene `pt_name` vacío. El nombre inglés no se usó como traducción portuguesa.
La consulta de [Full Salvo en Neuron, portugués](https://www.db.yugioh-card.com/yugiohdb/card_search.action?ope=2&cid=6622&request_locale=pt)
no proporcionó una ficha utilizable en esta ejecución.

## Cómo continuar

Buscar imágenes legibles por los set codes conservados y transcribir el nombre
con evidencia del ejemplar. La prioridad es la cara frontal de las Skill:
no confundir el personaje/reverso con el nombre de la habilidad. Una lectura
OCR por sí sola se guarda como propuesta; hace falta verificar la identidad
y el idioma. También hay que revisar si alguna impresión declarada por la
fuente es una inferencia de la colección, en lugar de un ejemplar documentado.

Reproducir con `research/investigate_name_gaps.py`; reutiliza el caché. No modifica
ninguna base. El informe de 104 casos permanece abierto, con causa documentada.
