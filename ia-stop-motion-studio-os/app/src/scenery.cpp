#include "scenery.h"

#include <QDateTime>
#include <QDir>
#include <QFileInfo>
#include <QImageReader>
#include <QJsonDocument>
#include <QJsonObject>
#include <QRandomGenerator>
#include <QRegularExpression>
#include <QSize>
#include <QStandardPaths>

namespace {

QString toolsDir()
{
    return qEnvironmentVariable("IA_SMS_HOME", QDir::homePath() + QStringLiteral("/IA-StopMotion")) + QStringLiteral("/ferramentas/sd");
}

struct Style {
    const char *id;
    const char *label;
    const char *prompt;
};

// Prompts are in English: that is what SD 1.5 was trained on.
const Style kStyles[] = {
    {"feltro", "Feltro e tecido", "handmade needle felted fabric diorama, felt and cloth textures, stop motion set, soft warm studio lighting, miniature, shallow depth of field"},
    {"massinha", "Massinha", "claymation set, plasticine clay miniature, handmade, stop motion animation background, soft studio lighting, fingerprints texture"},
    {"maquete", "Maquete de papelão", "handcrafted cardboard and paper miniature diorama, stop motion set, warm lamp lighting, tilt-shift"},
    {"papel", "Papel recortado", "layered paper cutout craft scene, papercraft, handmade, soft shadows, stop motion background"},
    {"pintura", "Cenário pintado", "hand painted theater backdrop, gouache illustration, storybook style, soft colors"},
    {"foto", "Foto realista", "photograph, natural light, detailed, 35mm"},
};

const char *kNegative = "people, person, character, text, watermark, signature, logo, blurry, lowres, deformed, jpeg artifacts";

} // namespace

SceneryStudio::SceneryStudio(QObject *parent)
    : QObject(parent)
{
    QDir().mkpath(baseDir());
    m_proc.setProcessChannelMode(QProcess::MergedChannels);
    connect(&m_proc, &QProcess::stateChanged, this, &SceneryStudio::busyChanged);
    connect(&m_proc, &QProcess::readyRead, this, [this] {
        // sd-cli draws "|=====>   | 7/20 - 1.23s/it" progress bars.
        static const QRegularExpression re(QStringLiteral("\\|\\s*(\\d+)/(\\d+)"));
        auto it = re.globalMatch(QString::fromUtf8(m_proc.readAll()));
        while (it.hasNext()) {
            const auto m = it.next();
            m_progress = m.captured(1).toDouble() / qMax(1.0, m.captured(2).toDouble());
            emit progressChanged();
            setStatus(tr("Gerando cenário: passo %1 de %2…").arg(m.captured(1), m.captured(2)));
        }
    });
    connect(&m_proc, &QProcess::finished, this, [this](int code, QProcess::ExitStatus st) {
        const bool ok = !m_cancelled && st == QProcess::NormalExit && code == 0 && !QImageReader(m_output).size().isEmpty();
        if (ok) {
            QFile meta(m_output + QStringLiteral(".json"));
            if (meta.open(QIODevice::WriteOnly))
                meta.write(m_meta);
            m_progress = 1;
            emit progressChanged();
            setStatus(tr("Cenário pronto."));
            emit itemsChanged();
            emit generated(QUrl::fromLocalFile(m_output));
        } else {
            QFile::remove(m_output);
            setStatus(m_cancelled ? tr("Geração cancelada.") : tr("stable-diffusion.cpp falhou (código %1).").arg(code));
            if (!m_cancelled)
                emit failed(m_status);
        }
    });
}

SceneryStudio::~SceneryStudio()
{
    cancel();
}

QString SceneryStudio::baseDir() const
{
    return qEnvironmentVariable("IA_SMS_HOME", QDir::homePath() + QStringLiteral("/IA-StopMotion")) + QStringLiteral("/Cenarios");
}

QString SceneryStudio::sdPath()
{
    const QString env = qEnvironmentVariable("IA_SMS_SD");
    const QString path = env.isEmpty() ? toolsDir() + QStringLiteral("/sd-cli") : env;
    if (QFileInfo(path).isExecutable())
        return path;
    return env.isEmpty() ? QStandardPaths::findExecutable(QStringLiteral("sd-cli")) : QString();
}

QString SceneryStudio::sdModel()
{
    const QString env = qEnvironmentVariable("IA_SMS_SD_MODEL");
    if (!env.isEmpty())
        return QFileInfo::exists(env) ? env : QString();
    const QDir dir(toolsDir());
    const QStringList models = dir.entryList({QStringLiteral("*.safetensors"), QStringLiteral("*.gguf"), QStringLiteral("*.ckpt")},
                                             QDir::Files, QDir::Name);
    return models.isEmpty() ? QString() : dir.absoluteFilePath(models.first());
}

QSize SceneryStudio::sizeFor(const QString &format)
{
    // SD 1.5 is trained at 512 px; keep the short side there (multiples of 8).
    if (format == QLatin1String("9:16"))
        return {432, 768};
    if (format == QLatin1String("1:1"))
        return {512, 512};
    return {768, 432};
}

QString SceneryStudio::stylePrompt(const QString &style, const QString &prompt)
{
    for (const Style &s : kStyles) {
        if (style == QLatin1String(s.id))
            return prompt.trimmed() + QStringLiteral(", ") + QString::fromLatin1(s.prompt);
    }
    return prompt.trimmed();
}

QVariantList SceneryStudio::styles() const
{
    QVariantList list;
    for (const Style &s : kStyles)
        list.append(QVariantMap{{QStringLiteral("id"), QString::fromLatin1(s.id)}, {QStringLiteral("label"), QString::fromUtf8(s.label)}});
    return list;
}

QVariantList SceneryStudio::items() const
{
    QVariantList list;
    const QDir dir(baseDir());
    for (const QFileInfo &fi : dir.entryInfoList({QStringLiteral("*.png"), QStringLiteral("*.jpg"), QStringLiteral("*.jpeg"),
                                                  QStringLiteral("*.webp")}, QDir::Files, QDir::Time)) {
        QString prompt;
        QFile meta(fi.absoluteFilePath() + QStringLiteral(".json"));
        if (meta.open(QIODevice::ReadOnly))
            prompt = QJsonDocument::fromJson(meta.readAll()).object().value(QStringLiteral("prompt")).toString();
        const QSize size = QImageReader(fi.absoluteFilePath()).size();
        list.append(QVariantMap{{QStringLiteral("url"), QUrl::fromLocalFile(fi.absoluteFilePath())},
                                {QStringLiteral("name"), fi.completeBaseName()},
                                {QStringLiteral("prompt"), prompt},
                                {QStringLiteral("generated"), !prompt.isEmpty()},
                                {QStringLiteral("size"), QStringLiteral("%1×%2").arg(size.width()).arg(size.height())}});
    }
    return list;
}

bool SceneryStudio::generate(const QString &prompt, const QString &style, const QString &format, int steps, int seed)
{
    if (busy() || prompt.trimmed().isEmpty())
        return false;
    if (!generatorAvailable()) {
        setStatus(tr("Geração de cenários não instalada: rode scripts/instalar-cenarios.sh"));
        emit failed(m_status);
        return false;
    }
    if (seed < 0)
        seed = int(QRandomGenerator::global()->bounded(1, 2147483647));
    const QSize size = sizeFor(format);
    const QString full = stylePrompt(style, prompt);
    m_output = baseDir() + QStringLiteral("/ia_%1.png").arg(QDateTime::currentDateTime().toString(QStringLiteral("yyyyMMdd-HHmmss-zzz")));
    m_meta = QJsonDocument(QJsonObject{{QStringLiteral("prompt"), prompt.trimmed()}, {QStringLiteral("style"), style},
                                       {QStringLiteral("fullPrompt"), full}, {QStringLiteral("seed"), seed},
                                       {QStringLiteral("steps"), steps}, {QStringLiteral("model"), QFileInfo(sdModel()).fileName()}})
                 .toJson();
    m_cancelled = false;
    m_progress = 0;
    emit progressChanged();
    setStatus(tr("Carregando o modelo…"));
    m_proc.start(sdPath(), {QStringLiteral("-m"), sdModel(), QStringLiteral("-p"), full,
                            QStringLiteral("-n"), QString::fromLatin1(kNegative),
                            QStringLiteral("--width"), QString::number(size.width()),
                            QStringLiteral("--height"), QString::number(size.height()),
                            QStringLiteral("--steps"), QString::number(qBound(1, steps, 60)),
                            QStringLiteral("--cfg-scale"), QStringLiteral("7"),
                            QStringLiteral("--sampling-method"), QStringLiteral("euler_a"),
                            QStringLiteral("-s"), QString::number(seed),
                            // Decoding in tiles keeps VRAM under 8 GB.
                            QStringLiteral("--vae-tiling"),
                            QStringLiteral("-o"), m_output});
    return true;
}

void SceneryStudio::cancel()
{
    if (!busy())
        return;
    m_cancelled = true;
    m_proc.kill();
    m_proc.waitForFinished(2000);
}

int SceneryStudio::importImages(const QList<QUrl> &urls)
{
    int n = 0;
    for (const QUrl &u : urls) {
        const QString src = u.isLocalFile() ? u.toLocalFile() : u.toString();
        QString dst = baseDir() + QLatin1Char('/') + QFileInfo(src).fileName();
        for (int i = 2; QFileInfo::exists(dst); ++i)
            dst = baseDir() + QStringLiteral("/%1_%2.%3").arg(QFileInfo(src).completeBaseName()).arg(i).arg(QFileInfo(src).suffix());
        if (QFile::copy(src, dst))
            ++n;
    }
    if (n)
        emit itemsChanged();
    return n;
}

bool SceneryStudio::remove(const QUrl &image)
{
    const QString file = image.toLocalFile();
    if (!file.startsWith(baseDir()))
        return false;
    const QString trash = baseDir() + QStringLiteral("/.lixeira");
    QDir().mkpath(trash);
    const bool ok = QFile::rename(file, trash + QLatin1Char('/') + QFileInfo(file).fileName());
    QFile::rename(file + QStringLiteral(".json"), trash + QLatin1Char('/') + QFileInfo(file).fileName() + QStringLiteral(".json"));
    emit itemsChanged();
    return ok;
}

void SceneryStudio::setStatus(const QString &s)
{
    if (s == m_status)
        return;
    m_status = s;
    emit statusChanged();
}
