#include "characters.h"
#include "imagetools.h"

#include <QDateTime>
#include <QDir>
#include <QFileInfo>
#include <QImageReader>
#include <QJsonDocument>
#include <QJsonObject>
#include <QRegularExpression>
#include <QSaveFile>

namespace {

const QStringList kShapes{QStringLiteral("A"), QStringLiteral("B"), QStringLiteral("C"), QStringLiteral("D"), QStringLiteral("E"),
                          QStringLiteral("F"), QStringLiteral("G"), QStringLiteral("H"), QStringLiteral("X")};

bool writeJson(const QString &path, const QJsonObject &obj)
{
    QSaveFile f(path);
    if (!f.open(QIODevice::WriteOnly))
        return false;
    f.write(QJsonDocument(obj).toJson());
    return f.commit();
}

QJsonObject readJson(const QString &path)
{
    QFile f(path);
    if (!f.open(QIODevice::ReadOnly))
        return {};
    return QJsonDocument::fromJson(f.readAll()).object();
}

} // namespace

CharacterLibrary::CharacterLibrary(QObject *parent)
    : QObject(parent)
{
    QDir().mkpath(baseDir());
}

QString CharacterLibrary::baseDir() const
{
    return qEnvironmentVariable("IA_SMS_HOME", QDir::homePath() + QStringLiteral("/IA-StopMotion")) + QStringLiteral("/Personagens");
}

QStringList CharacterLibrary::shapes() const
{
    return kShapes;
}

QVariantList CharacterLibrary::characters() const
{
    QVariantList list;
    const QDir dir(baseDir());
    for (const QFileInfo &info : dir.entryInfoList(QDir::Dirs | QDir::NoDotAndDotDot, QDir::Name)) {
        const QString path = info.absoluteFilePath();
        if (!QFileInfo::exists(path + QStringLiteral("/personagem.json")))
            continue;
        QVariantMap mouths;
        int count = 0;
        for (const QString &s : kShapes) {
            const QUrl url = mouthUrl(path, s);
            mouths.insert(s, url);
            count += url.isEmpty() ? 0 : 1;
        }
        QUrl thumb;
        if (QFileInfo::exists(path + QStringLiteral("/referencia.png"))) {
            thumb = QUrl::fromLocalFile(path + QStringLiteral("/referencia.png"));
            thumb.setQuery(QStringLiteral("v=%1").arg(m_rev));
        } else {
            thumb = mouths.value(QStringLiteral("D")).toUrl();
        }
        list.append(QVariantMap{{QStringLiteral("name"), characterName(path)}, {QStringLiteral("path"), path},
                                {QStringLiteral("mouths"), mouths}, {QStringLiteral("mouthCount"), count},
                                {QStringLiteral("thumbnail"), thumb}});
    }
    return list;
}

QString CharacterLibrary::characterName(const QString &dir) const
{
    return readJson(dir + QStringLiteral("/personagem.json")).value(QStringLiteral("name")).toString(QFileInfo(dir).fileName());
}

QString CharacterLibrary::createCharacter(const QString &name)
{
    QString clean = name.trimmed();
    clean.replace(QRegularExpression(QStringLiteral("[/\\\\:*?\"<>|]")), QStringLiteral("-"));
    if (clean.isEmpty())
        clean = tr("Personagem");
    QString path = baseDir() + QLatin1Char('/') + clean;
    for (int i = 2; QFileInfo::exists(path); ++i)
        path = baseDir() + QLatin1Char('/') + clean + QStringLiteral(" (%1)").arg(i);
    if (!QDir().mkpath(path + QStringLiteral("/bocas")))
        return {};
    writeJson(path + QStringLiteral("/personagem.json"),
              {{QStringLiteral("name"), QFileInfo(path).fileName()},
               {QStringLiteral("created"), QDateTime::currentDateTime().toString(Qt::ISODate)}});
    emit changed();
    return path;
}

bool CharacterLibrary::renameCharacter(const QString &dir, const QString &name)
{
    QJsonObject obj = readJson(dir + QStringLiteral("/personagem.json"));
    if (obj.isEmpty() || name.trimmed().isEmpty())
        return false;
    obj.insert(QStringLiteral("name"), name.trimmed());
    const bool ok = writeJson(dir + QStringLiteral("/personagem.json"), obj);
    emit changed();
    return ok;
}

bool CharacterLibrary::removeCharacter(const QString &dir)
{
    // Moved to a trash folder, not destroyed.
    const QString trash = baseDir() + QStringLiteral("/.lixeira");
    QDir().mkpath(trash);
    QString target = trash + QLatin1Char('/') + QFileInfo(dir).fileName();
    for (int i = 2; QFileInfo::exists(target); ++i)
        target = trash + QLatin1Char('/') + QFileInfo(dir).fileName() + QStringLiteral(" (%1)").arg(i);
    const bool ok = QDir().rename(dir, target);
    emit changed();
    return ok;
}

bool CharacterLibrary::setMouth(const QString &dir, const QString &shape, const QUrl &image)
{
    if (!kShapes.contains(shape))
        return false;
    QImageReader reader(image.isLocalFile() ? image.toLocalFile() : image.toString());
    reader.setAutoTransform(true);
    const QImage img = reader.read();
    if (img.isNull())
        return false;
    QDir().mkpath(dir + QStringLiteral("/bocas"));
    // Keep alpha (cut-out mouths); limit size so compositing stays fast.
    const QImage stored = img.width() > 1024 ? img.scaledToWidth(1024, Qt::SmoothTransformation) : img;
    const bool ok = stored.save(dir + QStringLiteral("/bocas/") + shape + QStringLiteral(".png"), "PNG");
    ++m_rev;
    emit changed();
    return ok;
}

bool CharacterLibrary::clearMouth(const QString &dir, const QString &shape)
{
    const bool ok = QFile::remove(dir + QStringLiteral("/bocas/") + shape + QStringLiteral(".png"));
    ++m_rev;
    emit changed();
    return ok;
}

bool CharacterLibrary::setReference(const QString &dir, const QUrl &image)
{
    QImageReader reader(image.isLocalFile() ? image.toLocalFile() : image.toString());
    reader.setAutoTransform(true);
    QImage img = reader.read();
    if (img.isNull())
        return false;
    if (img.width() > 800)
        img = img.scaledToWidth(800, Qt::SmoothTransformation);
    const bool ok = img.save(dir + QStringLiteral("/referencia.png"), "PNG");
    ++m_rev;
    emit changed();
    return ok;
}

QUrl CharacterLibrary::mouthUrl(const QString &dir, const QString &shape) const
{
    const QString file = dir + QStringLiteral("/bocas/") + shape + QStringLiteral(".png");
    if (dir.isEmpty() || !QFileInfo::exists(file))
        return {};
    QUrl url = QUrl::fromLocalFile(file);
    url.setQuery(QStringLiteral("v=%1").arg(m_rev));
    return url;
}

void CharacterLibrary::ensureDefault()
{
    if (!characters().isEmpty())
        return;
    const QString dir = createCharacter(tr("Boneco padrão"));
    if (dir.isEmpty())
        return;
    for (const QString &s : kShapes)
        ImageTools::defaultMouth(s).save(dir + QStringLiteral("/bocas/") + s + QStringLiteral(".png"), "PNG");
    ++m_rev;
    emit changed();
}
