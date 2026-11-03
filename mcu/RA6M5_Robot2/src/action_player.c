#include "action_player.h"
#include <stddef.h>
#include <string.h>

bool ap_pulse_valid(uint32_t joint, uint32_t pulse_us)
{
    static const uint16_t home[AP_JOINTS] = ROBOT_HOME_PULSES_US;
    static const uint16_t offsets[AP_JOINTS] = ROBOT_JOINT_OFFSETS_US;
    if (joint >= AP_JOINTS) { return false; }
    if (ROBOT_CALIBRATION_MODE != 0U)
    {
        if (joint == AP_BASE)
        { return (pulse_us >= ROBOT_BASE_MIN_US) && (pulse_us <= ROBOT_BASE_MAX_US); }
        return (pulse_us >= AP_MIN_US) && (pulse_us <= AP_MAX_US);
    }
    /* Numbered joint 3 is physically fixed; no action or SET/POSE may move it. */
    if (joint == 2U) { return pulse_us == ROBOT_JOINT3_FIXED_US; }
    uint32_t lower = (uint32_t) home[joint] - offsets[joint];
    uint32_t upper = (uint32_t) home[joint] + offsets[joint];
    if (lower < AP_MIN_US) { lower = AP_MIN_US; }
    if (upper > AP_MAX_US) { upper = AP_MAX_US; }
    /* Numbered joint 4 may move only on the positive side of its home command. */
    if ((joint == 3U) && (lower < ROBOT_JOINT4_MIN_US)) { lower = ROBOT_JOINT4_MIN_US; }
    if (joint == AP_BASE)
    {
        if (lower < ROBOT_BASE_MIN_US) { lower = ROBOT_BASE_MIN_US; }
        if (upper > ROBOT_BASE_MAX_US) { upper = ROBOT_BASE_MAX_US; }
    }
    return (pulse_us >= lower) && (pulse_us <= upper);
}

static bool valid_frame(const ap_frame_t * frame)
{
    if ((frame->duration_ms < 20U) || (frame->duration_ms > 60000U))
    {
        return false;
    }
    if ((frame->base_run_ms > frame->duration_ms) ||
        ((frame->base_run_ms != 0U) && (frame->pulse_us[AP_BASE] == 0U)))
    { return false; }
    for (uint32_t j = 0U; j < AP_JOINTS; ++j)
    {
        uint16_t value = frame->pulse_us[j];
        if ((value != 0U) && !ap_pulse_valid(j, value))
        {
            return false;
        }
    }
    return true;
}

void ap_init(ap_player_t * player, const ap_io_t * io)
{
    memset(player, 0, sizeof(*player));
    player->io = *io;
    player->state = AP_IDLE;
}

ap_result_t ap_stop(ap_player_t * player)
{
    uint16_t enabled = player->io.cancel_pending();
    bool failed = (player->state == AP_FAULT);
    for (uint32_t j = 0U; j < AP_JOINTS; ++j)
    {
        if ((enabled & (1U << j)) == 0U)
        {
            player->pulse[j] = 0U;
        }
    }
    if (player->pulse[AP_BASE] != 0U)
    {
        if (player->io.write(AP_BASE, AP_BASE_STOP_US, false))
        {
            player->pulse[AP_BASE] = AP_BASE_STOP_US;
        }
        else
        {
            failed = true;
        }
    }
    player->state = failed ? AP_FAULT : AP_IDLE;
    return failed ? AP_IO_ERROR : AP_OK;
}

static ap_result_t fault(ap_player_t * player)
{
    player->state = AP_FAULT;
    (void) ap_stop(player);
    return AP_IO_ERROR;
}

static ap_result_t begin_frame(ap_player_t * player, uint32_t now)
{
    bool arming = false;
    for (uint32_t j = 0U; j < AP_JOINTS; ++j)
    {
        uint16_t value = player->frames[player->frame].pulse_us[j];
        player->from[j] = player->pulse[j];
        player->target[j] = (value != 0U) ? value : player->pulse[j];
        if ((player->pulse[j] == 0U) && (value != 0U))
        {
            if (!player->io.write(j, value, true))
            {
                return fault(player);
            }
            /* First activation has no measured starting angle to interpolate from. */
            player->pulse[j] = value;
            player->from[j] = value;
            arming = true;
        }
    }
    player->state = arming ? AP_ARMING : AP_MOVING;
    player->started = now;
    player->updated = now - 20U;
    return AP_OK;
}

ap_result_t ap_start(ap_player_t * player, const ap_frame_t * frames,
                     uint32_t count, uint32_t now)
{
    if (player->state == AP_FAULT)
    {
        return AP_IO_ERROR;
    }
    if (player->state != AP_IDLE)
    {
        return AP_BUSY;
    }
    if ((frames == NULL) || (count == 0U) || (count > 1024U))
    {
        return AP_INVALID;
    }
    /* Validate the WHOLE group before any output changes. */
    for (uint32_t i = 0U; i < count; ++i)
    {
        if (!valid_frame(&frames[i]))
        {
            return AP_INVALID;
        }
    }
    player->frames = frames;
    player->count = count;
    player->frame = 0U;
    return begin_frame(player, now);
}

ap_result_t ap_tick(ap_player_t * player, uint32_t now)
{
    if (player->state == AP_FAULT)
    {
        return AP_IO_ERROR;
    }
    if (player->state == AP_IDLE)
    {
        return AP_OK;
    }
    if (player->state == AP_ARMING)
    {
        int ready = player->io.ready();
        if ((ready < 0) || ((uint32_t) (now - player->started) > 100U))
        {
            return fault(player);
        }
        if (ready == 0)
        {
            return AP_OK;
        }
        player->state = AP_MOVING;
        player->started = now;
        player->updated = now - 20U;
    }
    uint32_t elapsed = now - player->started;
    uint32_t duration = player->frames[player->frame].duration_ms;
    if (((uint32_t) (now - player->updated) < 20U) && (elapsed < duration))
    {
        return AP_OK;
    }
    player->updated = now;
    uint32_t progress = (elapsed < duration) ? elapsed : duration;
    for (uint32_t j = 0U; j < AP_JOINTS; ++j)
    {
        if (player->target[j] == 0U)
        {
            continue;
        }
        int32_t delta = (int32_t) player->target[j] - (int32_t) player->from[j];
        uint16_t value = (j == AP_BASE) ? player->target[j] :
            (uint16_t) ((int32_t) player->from[j] +
                        delta * (int32_t) progress / (int32_t) duration);
        uint32_t base_run = player->frames[player->frame].base_run_ms;
        if ((j == AP_BASE) && (base_run != 0U) && (elapsed >= base_run))
        { value = AP_BASE_STOP_US; }
        if (value != player->pulse[j])
        {
            if (!player->io.write(j, value, false))
            {
                return fault(player);
            }
            player->pulse[j] = value;
        }
    }
    if (elapsed >= duration)
    {
        ++player->frame;
        if (player->frame >= player->count)
        {
            return (ap_stop(player) == AP_OK) ? AP_DONE : AP_IO_ERROR;
        }
        return begin_frame(player, now);
    }
    return AP_OK;
}

static const char * skip_space(const char * p)
{
    while ((*p == ' ') || (*p == '\t')) { ++p; }
    return p;
}

static bool number(const char ** cursor, uint32_t * value)
{
    const char * p = skip_space(*cursor);
    if ((*p < '0') || (*p > '9')) { return false; }
    uint32_t result = 0U;
    do
    {
        uint32_t digit = (uint32_t) (*p - '0');
        if (result > (UINT32_MAX - digit) / 10U) { return false; }
        result = result * 10U + digit;
        ++p;
    } while ((*p >= '0') && (*p <= '9'));
    if ((*p != '\0') && (*p != ' ') && (*p != '\t')) { return false; }
    *cursor = p;
    *value = result;
    return true;
}

bool ap_parse(const char * line, ap_command_t * command)
{
    memset(command, 0, sizeof(*command));
    const char * p = skip_space(line);
    size_t length = strlen(p);
    while ((length != 0U) && ((p[length - 1U] == ' ') || (p[length - 1U] == '\t')))
    { --length; }
    if ((length == 4U) && (strncmp(p, "PING", 4U) == 0)) { command->kind = CMD_PING; }
    else if ((length == 6U) && (strncmp(p, "STATUS", 6U) == 0)) { command->kind = CMD_STATUS; }
    else if ((length == 7U) && (strncmp(p, "CAPTURE", 7U) == 0)) { command->kind = CMD_CAPTURE; }
    else if ((length == 4U) && (strncmp(p, "STOP", 4U) == 0)) { command->kind = CMD_STOP; }
    else if (((length == 5U) && (strncmp(p, "ACT0", 4U) == 0) && (p[4] >= '1') && (p[4] <= '6')) ||
             ((length == 2U) && (p[0] == '0') && (p[1] >= '1') && (p[1] <= '6')))
    {
        command->kind = CMD_ACTION;
        command->group_id = (uint32_t) (p[(length == 5U) ? 4U : 1U] - '0');
    }
    else if (((length == 5U) && (strncmp(p, "START", 5U) == 0)) ||
             ((length == 4U) && (strncmp(p, "SHOW", 4U) == 0)))
    { command->kind = CMD_SHOW; }
    else if ((strncmp(p, "POSE", 4U) == 0) && ((p[4] == ' ') || (p[4] == '\t')))
    {
        p += 4;
        if (!number(&p, &command->pose.duration_ms)) { return false; }
        for (uint32_t j = 0U; j < AP_JOINTS; ++j)
        {
            uint32_t value;
            if (!number(&p, &value) || (value > UINT16_MAX)) { return false; }
            command->pose.pulse_us[j] = (uint16_t) value;
        }
        if ((*skip_space(p) != '\0') || !valid_frame(&command->pose)) { return false; }
        command->kind = CMD_POSE;
    }
    else if ((strncmp(p, "SET", 3U) == 0) && ((p[3] == ' ') || (p[3] == '\t')))
    {
        p += 3;
        uint32_t joint;
        uint32_t value;
        if (!number(&p, &joint) || !number(&p, &value) ||
            !number(&p, &command->pose.duration_ms)) { return false; }
        if ((*skip_space(p) != '\0') || (joint < 1U) || (joint > AP_JOINTS) ||
            !ap_pulse_valid(joint - 1U, value)) { return false; }
        command->pose.pulse_us[joint - 1U] = (uint16_t) value;
        if (!valid_frame(&command->pose)) { return false; }
        command->kind = CMD_SET;
    }
    else { return false; }
    return true;
}
