#pragma once

#include <QObject>
#include <QUrl>
#include <QVariantList>

// Character library (<base>/Personagens/<nome>/): reference photo and the nine
// replacement mouths used by lip sync (Rhubarb shapes A–H and X), stored as
// bocas/<shape>.png. Shared by all projects.
class CharacterLibrary : public QObject
{
    Q_OBJECT
    Q_PROPERTY(QVariantList characters READ characters NOTIFY changed)
    Q_PROPERTY(QStringList shapes READ shapes CONSTANT)

public:
    explicit CharacterLibrary(QObject *parent = nullptr);

    QVariantList characters() const;
    QStringList shapes() const;
    QString baseDir() const;

    Q_INVOKABLE QString createCharacter(const QString &name);
    Q_INVOKABLE bool renameCharacter(const QString &dir, const QString &name);
    Q_INVOKABLE bool removeCharacter(const QString &dir);
    Q_INVOKABLE bool setMouth(const QString &dir, const QString &shape, const QUrl &image);
    Q_INVOKABLE bool clearMouth(const QString &dir, const QString &shape);
    Q_INVOKABLE bool setReference(const QString &dir, const QUrl &image);
    Q_INVOKABLE QUrl mouthUrl(const QString &dir, const QString &shape) const;
    Q_INVOKABLE QString characterName(const QString &dir) const;
    // Creates "Boneco padrão" with drawn felt mouths when the library is empty.
    Q_INVOKABLE void ensureDefault();

signals:
    void changed();

private:
    int m_rev = 0; // cache busting for replaced images
};
