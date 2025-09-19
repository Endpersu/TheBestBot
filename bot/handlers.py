import os
import html
import logging
from telegram import Update
from telegram.ext import (
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
    Application,
)

from . import network
from . import storage

LOG = logging.getLogger(__name__)


def format_network_info() -> str:
    ssid = network.get_wifi_ssid()
    ip, gw = network.parse_ipconfig_for_gateway_and_ip()
    local_ip = network.get_local_ip()

    lines = ["<b>Сетевой отчёт</b>", ""]
    if ssid:
        lines.append(f"🔸 <b>Имя сети (SSID):</b> <code>{html.escape(ssid)}</code>")
    else:
        lines.append("🔸 <b>Имя сети (SSID):</b> <i>Не подключено / не найдено</i>")

    if ip:
        lines.append(f"🔹 <b>Локальный IP (adapter):</b> <code>{html.escape(ip)}</code>")
    else:
        lines.append("🔹 <b>Локальный IP (adapter):</b> <i>Не найден</i>")

    lines.append(f"🔹 <b>Определённый IP (метод UDP):</b> <code>{html.escape(local_ip)}</code>")

    if gw:
        lines.append(f"🔸 <b>Шлюз (Default Gateway):</b> <code>{html.escape(gw)}</code>")
    else:
        lines.append("🔸 <b>Шлюз (Default Gateway):</b> <i>Не найден</i>")

    lines.append("")
    lines.append("Чтобы посмотреть сохранённые Wi‑Fi профили используйте: <code>/wifiprofiles</code>")
    lines.append("Чтобы увидеть пароль профиля: <code>/wifipass имя_профиля</code>")
    lines.append("Внимание: отображение паролей требует прав и доступно только на локальной машине.")
    return "\n".join(lines)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    LOG.info("/start from chat_id=%s user=%s", update.effective_chat.id if update.effective_chat else None, update.effective_user and update.effective_user.id)
    text = (
        "<b>Привет! Я — бот-помощник.</b>\n\n"
        "Я умею несколько команд. Ниже краткое описание и форматы данных, которые я принимаю.\n\n"
        "🔹 <b>/start</b> — это сообщение помощи (вы уже здесь).\n\n"
        "🔹 <b>/find_net номер_павильона</b> — найти информацию по номеру павильона.\n"
        "   Пример: <code>/find_net A12</code> или просто отправьте номер павильона как текст после команды.\n\n"
        "🔹 <b>/add_data</b> — добавить запись в базу данных. Отправьте JSON в одном сообщении в следующем формате:\n"
        "   <code>{\"pavilion\": \"A12\", \"name\": \"Продавец\", \"note\": \"Комментарий\"}</code>\n"
        "   Поля нестрого обязательны — главное, чтобы сообщение было корректным JSON-объектом.\n\n"
        "Если у вас вопросы, используйте <code>/help</code> или просто напишите сообщение — я постараюсь помочь."
    )
    # Use reply_html to keep existing behaviour (HTML formatting)
    await update.message.reply_html(text)


async def network_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    LOG.info("/network requested by chat_id=%s", update.effective_chat.id if update.effective_chat else None)
    text = format_network_info()
    await update.message.reply_html(text)


async def wifiprofiles_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    LOG.info("/wifiprofiles requested by chat_id=%s", update.effective_chat.id if update.effective_chat else None)
    profiles = network.list_wifi_profiles()
    if not profiles:
        await update.message.reply_html("<i>Сохранённых Wi‑Fi профилей не найдено.</i>")
        return
    lines = ["<b>Сохранённые Wi‑Fi профили:</b>"]
    for p in profiles:
        lines.append(f"• <code>{html.escape(p)}</code>")
    lines.append("\nИспользуйте: <code>/wifipass имя_профиля</code>")
    await update.message.reply_html("\n".join(lines))


async def wifipass_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    LOG.info("/wifipass requested by chat_id=%s args=%s", update.effective_chat.id if update.effective_chat else None, context.args)
    args = context.args
    if not args:
        await update.message.reply_html("Использование: <code>/wifipass имя_профиля</code>")
        return
    profile = " ".join(args)
    pwd = network.get_wifi_password(profile)
    if pwd:
        LOG.info("Found password for profile %s (len=%d)", profile, len(pwd))
        await update.message.reply_html(f"<b>Пароль для</b> <code>{html.escape(profile)}</code>:\n<code>{html.escape(pwd)}</code>")
    else:
        LOG.info("Password for profile %s not found", profile)
        await update.message.reply_html(f"Не удалось найти пароль для <code>{html.escape(profile)}</code> (или отсутствуют права).")


async def wifipass_all_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    LOG.info("/wifipass_all requested by chat_id=%s", update.effective_chat.id if update.effective_chat else None)
    profiles = network.list_wifi_profiles()
    if not profiles:
        await update.message.reply_html("<i>Сохранённых Wi‑Fi профилей не найдено.</i>")
        return
    lines = ["<b>Пароли Wi‑Fi (если доступны):</b>"]
    for p in profiles:
        pwd = network.get_wifi_password(p) or "<i>Не найден / закрыт</i>"
        lines.append(f"• <code>{html.escape(p)}</code>: <code>{html.escape(pwd)}</code>")
    await update.message.reply_html("\n".join(lines))


def build_application(token: str) -> Application:
    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("network", network_command))
    app.add_handler(CommandHandler("wifiprofiles", wifiprofiles_command))
    app.add_handler(CommandHandler("wifipass", wifipass_command))
    app.add_handler(CommandHandler("wifipass_all", wifipass_all_command))

    # Table conversation
    NAME, ADDRESS, PASSWORD, NOTE = range(4)


    async def fill_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
        LOG.info("/fill start by chat_id=%s", update.effective_chat.id if update.effective_chat else None)
        await update.message.reply_html("<b>Заполнение записи.</b> Введите имя сети (SSID) или отправьте /skip, чтобы пропустить.")
        return NAME


    async def fill_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = update.message.text.strip() if update.message and update.message.text else ""
        context.user_data['name'] = text or "Отсутствует"
        await update.message.reply_html("Введите адрес (IP) или отправьте /skip, чтобы пропустить.")
        return ADDRESS


    async def fill_address(update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = update.message.text.strip() if update.message and update.message.text else ""
        context.user_data['address'] = text or "Отсутствует"
        await update.message.reply_html("Введите пароль (если есть) или отправьте /skip.")
        return PASSWORD


    async def fill_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = update.message.text.strip() if update.message and update.message.text else ""
        context.user_data['password'] = text or "Отсутствует"
        await update.message.reply_html("Введите примечание или отправьте /skip.")
        return NOTE


    async def fill_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = update.message.text.strip() if update.message and update.message.text else ""
        context.user_data['note'] = text or "Отсутствует"
        storage.save_row(os.path.dirname(__file__), context.user_data)
        LOG.info("Saved fill entry: %s", {k: context.user_data.get(k) for k in ('name','address')})
        await update.message.reply_html("Запись сохранена в таблицу.")
        return ConversationHandler.END


    async def skip_field(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if 'name' not in context.user_data:
            context.user_data['name'] = "Отсутствует"
            await update.message.reply_html("Пропущено. Введите адрес (IP) или /skip.")
            return ADDRESS
        if 'address' not in context.user_data:
            context.user_data['address'] = "Отсутствует"
            await update.message.reply_html("Пропущено. Введите пароль или /skip.")
            return PASSWORD
        if 'password' not in context.user_data:
            context.user_data['password'] = "Отсутствует"
            await update.message.reply_html("Пропущено. Введите примечание или /skip.")
            return NOTE
        context.user_data['note'] = "Отсутствует"
        storage.save_row(os.path.dirname(__file__), context.user_data)
        LOG.info("Saved fill entry (skipped fields): %s", {k: context.user_data.get(k) for k in ('name','address')})
        await update.message.reply_html("Запись сохранена в таблицу.")
        return ConversationHandler.END


    async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
        LOG.info("/cancel by chat_id=%s", update.effective_chat.id if update.effective_chat else None)
        await update.message.reply_html("Заполнение отменено.")
        return ConversationHandler.END


    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('fill', fill_start)],
        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, fill_name), CommandHandler('skip', skip_field)],
            ADDRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, fill_address), CommandHandler('skip', skip_field)],
            PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, fill_password), CommandHandler('skip', skip_field)],
            NOTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, fill_note), CommandHandler('skip', skip_field)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    app.add_handler(conv_handler)


    async def showtable(update: Update, context: ContextTypes.DEFAULT_TYPE):
        LOG.info("/showtable requested by chat_id=%s", update.effective_chat.id if update.effective_chat else None)
        rows = storage.load_table(os.path.dirname(__file__))
        if not rows:
            await update.message.reply_html("<i>Таблица пуста.</i>")
            return
        lines = ["<b>Таблица записей:</b>"]
        for i, r in enumerate(rows, 1):
            lines.append(f"{i}. SSID: <code>{html.escape(r.get('name','Отсутствует'))}</code> | IP: <code>{html.escape(r.get('address','Отсутствует'))}</code> | Пароль: <code>{html.escape(r.get('password','Отсутствует'))}</code> | Прим: <code>{html.escape(r.get('note','Отсутствует'))}</code>")
        await app.bot.send_message(chat_id=update.effective_chat.id, text="\n".join(lines), parse_mode="HTML")

    app.add_handler(CommandHandler('showtable', showtable))

    return app
