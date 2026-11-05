# Registro de cambios

## 2.0.0 — Etapa 1 (base sólida)
Se parte del proyecto 1.1.1 sin eliminar ninguna función.

### Añadido
- **Biblioteca completa** (1.1.1): sincroniza también los juegos que posees y no tienes instalados (Steam con clave de API,
  Epic con `legendary`, Ubisoft/EA/Xbox/Battle.net/GOG vía GOG Galaxy 2.0). Filtro Todos/Instalados/No instalados y botón INSTALAR.
- **Colecciones**: crea, renombra y elimina colecciones; añade juegos desde el clic derecho; filtra la biblioteca por colección.
- **Perfil**: avatar, nombre, descripción, **nivel y experiencia**, insignias, juegos favoritos, **desafíos diarios y semanales** e
  **historial de actividad**. 20 logros (11 de juego + 9 por usar Gamesword) con XP; avisos al desbloquear.
- **Copias de seguridad**: copia diaria automática (se guardan 7), copia manual, restauración con copia previa de seguridad,
  comprobación de integridad al arrancar y **recuperación automática** de la última copia buena si la base está dañada. Sin claves.
- **Gamesword AI**: confirmación con botones antes de acciones importantes (cerrar un juego, quitarlo de la biblioteca, borrar la
  memoria); «cierra el juego que tengo abierto»; **memoria configurable** («recuerda que…», ver/borrar en Ajustes);
  **comandos personalizados** («modo noche» → Discord y Rocket League); comprensión de frases más libres; **diagnóstico del PC**
  (CPU, RAM, GPU NVIDIA, disco y procesos) con avisos concretos; nuevas herramientas para el modelo.
- **Personalización**: modo compacto, colores principal y secundario a elegir y restablecer.
- 22 tests nuevos (59 en total) y prueba de humo de interfaz.

### Cambiado
- Los logros de *Estadísticas* ahora salen del sistema de progreso (se guardan con fecha y dan XP).
- La IA ya no cierra nada sin confirmación.

## 1.1.1 — 1.1.0
Ver historial en el README: seguridad con keyring, Xbox/Battle.net/Rockstar, bandeja, atajos, mando, Rich Presence, IA con
herramientas y streaming, Whisper local, rendimiento, cuentas y chat de grupo, actualizaciones, licencias.

## Pendiente (siguientes etapas)
- **Etapa 2 — Comunidad**: solicitudes de amistad, chat privado, bloqueo, denuncias y moderación en el servidor.
- **Etapa 3 — Rendimiento**: gráficas con historial, perfiles por juego, alertas configurables, overlay externo.
- **Etapa 4 — Personalización avanzada**: fondos, widgets del panel, sonidos, notificaciones, menú configurable.
