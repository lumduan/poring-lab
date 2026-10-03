// S2 spike: the C layout of every moonlight-common-c struct the ctypes bindings mirror, as JSON.
// limelight.py refuses to start if its ctypes structs differ (a silent offset mismatch would send
// garbage to the host). Built and run against the PINNED headers in the image's builder stage.
#include <stddef.h>
#include <stdio.h>
#include "Limelight.h"

static int first;
#define BEGIN(T) do { printf("%s  \"%s\": {\"size\": %zu, \"offsets\": {", \
                             first ? "" : ",\n", #T, sizeof(T)); first = 0; } while (0)
#define F(T, f, sep) printf("%s\"%s\": %zu", sep, #f, offsetof(T, f))
#define END() printf("}}")
#define C(name, sep) printf("%s\"%s\": %lld", sep, #name, (long long)(name))

int main(void) {
    first = 1;
    printf("{\"structs\": {\n");
    BEGIN(STREAM_CONFIGURATION);
    F(STREAM_CONFIGURATION, width, ""); F(STREAM_CONFIGURATION, height, ", ");
    F(STREAM_CONFIGURATION, fps, ", "); F(STREAM_CONFIGURATION, bitrate, ", ");
    F(STREAM_CONFIGURATION, packetSize, ", "); F(STREAM_CONFIGURATION, streamingRemotely, ", ");
    F(STREAM_CONFIGURATION, audioConfiguration, ", ");
    F(STREAM_CONFIGURATION, supportedVideoFormats, ", ");
    F(STREAM_CONFIGURATION, clientRefreshRateX100, ", ");
    F(STREAM_CONFIGURATION, colorSpace, ", "); F(STREAM_CONFIGURATION, colorRange, ", ");
    F(STREAM_CONFIGURATION, encryptionFlags, ", ");
    F(STREAM_CONFIGURATION, remoteInputAesKey, ", ");
    F(STREAM_CONFIGURATION, remoteInputAesIv, ", ");
    END();
    BEGIN(SERVER_INFORMATION);
    F(SERVER_INFORMATION, address, ""); F(SERVER_INFORMATION, serverInfoAppVersion, ", ");
    F(SERVER_INFORMATION, serverInfoGfeVersion, ", "); F(SERVER_INFORMATION, rtspSessionUrl, ", ");
    F(SERVER_INFORMATION, serverCodecModeSupport, ", ");
    END();
    BEGIN(LENTRY);
    F(LENTRY, next, ""); F(LENTRY, data, ", "); F(LENTRY, length, ", ");
    F(LENTRY, bufferType, ", ");
    END();
    BEGIN(DECODE_UNIT);
    F(DECODE_UNIT, frameNumber, ""); F(DECODE_UNIT, frameType, ", ");
    F(DECODE_UNIT, frameHostProcessingLatency, ", "); F(DECODE_UNIT, receiveTimeMs, ", ");
    F(DECODE_UNIT, enqueueTimeMs, ", "); F(DECODE_UNIT, presentationTimeMs, ", ");
    F(DECODE_UNIT, fullLength, ", "); F(DECODE_UNIT, bufferList, ", ");
    F(DECODE_UNIT, hdrActive, ", "); F(DECODE_UNIT, colorspace, ", ");
    END();
    BEGIN(DECODER_RENDERER_CALLBACKS);
    F(DECODER_RENDERER_CALLBACKS, setup, ""); F(DECODER_RENDERER_CALLBACKS, start, ", ");
    F(DECODER_RENDERER_CALLBACKS, stop, ", "); F(DECODER_RENDERER_CALLBACKS, cleanup, ", ");
    F(DECODER_RENDERER_CALLBACKS, submitDecodeUnit, ", ");
    F(DECODER_RENDERER_CALLBACKS, capabilities, ", ");
    END();
    BEGIN(AUDIO_RENDERER_CALLBACKS);
    F(AUDIO_RENDERER_CALLBACKS, init, ""); F(AUDIO_RENDERER_CALLBACKS, start, ", ");
    F(AUDIO_RENDERER_CALLBACKS, stop, ", "); F(AUDIO_RENDERER_CALLBACKS, cleanup, ", ");
    F(AUDIO_RENDERER_CALLBACKS, decodeAndPlaySample, ", ");
    F(AUDIO_RENDERER_CALLBACKS, capabilities, ", ");
    END();
    BEGIN(CONNECTION_LISTENER_CALLBACKS);
    F(CONNECTION_LISTENER_CALLBACKS, stageStarting, "");
    F(CONNECTION_LISTENER_CALLBACKS, stageComplete, ", ");
    F(CONNECTION_LISTENER_CALLBACKS, stageFailed, ", ");
    F(CONNECTION_LISTENER_CALLBACKS, connectionStarted, ", ");
    F(CONNECTION_LISTENER_CALLBACKS, connectionTerminated, ", ");
    F(CONNECTION_LISTENER_CALLBACKS, logMessage, ", ");
    F(CONNECTION_LISTENER_CALLBACKS, rumble, ", ");
    F(CONNECTION_LISTENER_CALLBACKS, connectionStatusUpdate, ", ");
    F(CONNECTION_LISTENER_CALLBACKS, setHdrMode, ", ");
    F(CONNECTION_LISTENER_CALLBACKS, rumbleTriggers, ", ");
    F(CONNECTION_LISTENER_CALLBACKS, setMotionEventState, ", ");
    F(CONNECTION_LISTENER_CALLBACKS, setControllerLED, ", ");
    END();
    printf("\n}, \"constants\": {");
    C(CAPABILITY_PULL_RENDERER, ""); C(ENCFLG_ALL, ", "); C(ENCFLG_AUDIO, ", ");
    C(VIDEO_FORMAT_H264, ", "); C(AUDIO_CONFIGURATION_STEREO, ", "); C(SCM_H264, ", ");
    C(STREAM_CFG_LOCAL, ", "); C(COLORSPACE_REC_601, ", "); C(COLOR_RANGE_LIMITED, ", ");
    C(BUTTON_ACTION_PRESS, ", "); C(BUTTON_ACTION_RELEASE, ", "); C(BUTTON_LEFT, ", ");
    C(BUTTON_MIDDLE, ", "); C(BUTTON_RIGHT, ", "); C(BUTTON_X1, ", "); C(BUTTON_X2, ", ");
    C(KEY_ACTION_DOWN, ", "); C(KEY_ACTION_UP, ", ");
    C(MODIFIER_SHIFT, ", "); C(MODIFIER_CTRL, ", "); C(MODIFIER_ALT, ", "); C(MODIFIER_META, ", ");
    C(DR_OK, ", "); C(ML_ERROR_GRACEFUL_TERMINATION, ", ");
    printf("}}\n");
    return 0;
}
