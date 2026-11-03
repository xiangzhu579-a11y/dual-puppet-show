#ifndef ACTION_PLAYER_H
#define ACTION_PLAYER_H

#include <stdbool.h>
#include <stdint.h>
#include "robot_config.h"

#define AP_JOINTS       (13U)
#define AP_BASE         (12U)
#define AP_MIN_US       ROBOT_MIN_PULSE_US
#define AP_MAX_US       ROBOT_MAX_PULSE_US
#define AP_BASE_STOP_US ROBOT_BASE_STOP_US

typedef struct
{
    uint32_t duration_ms;
    uint16_t pulse_us[AP_JOINTS]; /* 0 = keep current / leave inactive. */
    uint32_t base_run_ms; /* 0: normal frame hold; >0: timed base motion then neutral. */
} ap_frame_t;

typedef struct
{
    bool (*write)(uint32_t joint, uint16_t pulse_us, bool first);
    int (*ready)(void); /* -1 fault; 0 waiting; 1 all new pins enabled. */
    uint16_t (*cancel_pending)(void); /* Return pins physically enabled. */
} ap_io_t;

typedef enum { AP_IDLE, AP_ARMING, AP_MOVING, AP_FAULT } ap_state_t;
typedef enum { AP_OK, AP_BUSY, AP_INVALID, AP_IO_ERROR, AP_DONE } ap_result_t;
typedef struct
{
    ap_io_t io;
    ap_state_t state;
    const ap_frame_t * frames;
    uint32_t count;
    uint32_t frame;
    uint32_t started;
    uint32_t updated;
    uint16_t pulse[AP_JOINTS]; /* Software command values, not feedback. */
    uint16_t from[AP_JOINTS];
    uint16_t target[AP_JOINTS];
} ap_player_t;

typedef enum { CMD_INVALID, CMD_PING, CMD_STATUS, CMD_STOP, CMD_ACTION, CMD_SHOW,
               CMD_POSE, CMD_SET, CMD_CAPTURE } ap_command_kind_t;
typedef struct
{
    ap_command_kind_t kind;
    uint32_t group_id;
    ap_frame_t pose;
} ap_command_t;

void ap_init(ap_player_t * player, const ap_io_t * io);
bool ap_pulse_valid(uint32_t joint, uint32_t pulse_us);
ap_result_t ap_start(ap_player_t * player, const ap_frame_t * frames,
                     uint32_t count, uint32_t now);
ap_result_t ap_tick(ap_player_t * player, uint32_t now);
ap_result_t ap_stop(ap_player_t * player);
bool ap_parse(const char * line, ap_command_t * command);

#endif
