#pragma once

#include <QList>
#include <QString>
#include <QStringList>

// Read-only view of a stop-motion project on disk, used by the timeline to
// place captured scenes (possibly from other projects) into a film.
struct Scene
{
    struct Frame {
        QString file; // absolute path
        int hold = 1;
    };

    QString dir;
    QString name;
    int fps = 12;
    QList<Frame> frames;
    QString audio;         // absolute path, empty if none
    int audioOffset = 0;   // scene frame where the audio starts
    bool deflicker = false;

    bool isValid() const { return !frames.isEmpty(); }
    int totalFrames() const;
    double seconds() const { return fps > 0 ? double(totalFrames()) / fps : 0.0; }
    // Photo shown at a given time, honouring per-photo holds.
    int frameIndexAt(double seconds) const;

    static Scene load(const QString &dir);
    // FFmpeg concat-demuxer list with one "duration" per photo.
    bool writeConcatList(const QString &path) const;
    // FFmpeg filters applied to the photos before scaling ("" or "...,").
    QString filterPrefix() const;
    // FFmpeg input/mapping arguments that add the soundtrack, cut to the
    // animation length. Empty when the scene has no audio.
    QStringList audioInputArgs() const;
    QStringList audioOutputArgs() const;
};
