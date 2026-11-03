#include "hal_data.h"
#include "action_player.h"
#include "action_groups.h"
#include <stdio.h>
#include <string.h>

#define TIMER_COUNT (7U)
#define PERIOD_US (20000U)
#define PORT_COUNT (2U)
#define RX_SIZE (512U)
#define TX_SIZE (2048U)
#define LINE_SIZE (160U)

void SysTick_Handler(void);
void R_BSP_WarmStart(bsp_warm_start_event_t event);

volatile uint32_t g_app_ms = 0U;
volatile fsp_err_t g_servo_error = FSP_SUCCESS;
volatile fsp_err_t g_uart_error[PORT_COUNT] = {FSP_SUCCESS, FSP_SUCCESS};
volatile uint32_t g_servo_stage = 0U; /* 10 idle, 15 arming, 20 playing, 99 fault */
volatile uint32_t g_servo_enabled_mask = 0U;
volatile uint32_t g_servo_applied_us[AP_JOINTS];
volatile uint32_t g_action_frame = 0U;
volatile uint32_t g_action_command = 0U; /* debugger: 1 ACT01, 2 STOP */
volatile uint32_t g_action_select = 1U; /* command 1 selects ACT01..06; command 3 plays SHOW. */
volatile uint32_t g_action_group = 0U; /* 0 boot pose, 1..6 source action groups */
volatile uint32_t g_show_running = 0U;
volatile uint32_t g_uart_rx_errors[PORT_COUNT];
volatile uint32_t g_uart_tx_dropped[PORT_COUNT];

typedef struct
{
    uint32_t timer;
    gpt_io_pin_t output;
    bsp_io_port_pin_t pin;
} joint_pin_t;

static const timer_instance_t * const s_timers[TIMER_COUNT] =
{
    &g_servo_pwm0, &g_servo_pwm1, &g_servo_pwm, &g_servo_pwm4,
    &g_servo_pwm5, &g_servo_pwm6, &g_servo_pwm7
};
static const joint_pin_t s_joint[AP_JOINTS] =
{
    {0U, GPT_IO_PIN_GTIOCB, BSP_IO_PORT_05_PIN_11}, /* 1 head_yaw */
    {1U, GPT_IO_PIN_GTIOCA, BSP_IO_PORT_01_PIN_09}, /* 2 torso_yaw */
    {1U, GPT_IO_PIN_GTIOCB, BSP_IO_PORT_01_PIN_10}, /* 3 torso_pitch_low */
    {3U, GPT_IO_PIN_GTIOCA, BSP_IO_PORT_03_PIN_02}, /* 4 torso_pitch_high */
    {0U, GPT_IO_PIN_GTIOCA, BSP_IO_PORT_05_PIN_12}, /* 5 L_shoulder */
    {3U, GPT_IO_PIN_GTIOCB, BSP_IO_PORT_03_PIN_01}, /* 6 L_elbow */
    {4U, GPT_IO_PIN_GTIOCA, BSP_IO_PORT_02_PIN_03}, /* 7 L_wrist_pitch */
    {4U, GPT_IO_PIN_GTIOCB, BSP_IO_PORT_02_PIN_02}, /* 8 L_wrist_yaw */
    {5U, GPT_IO_PIN_GTIOCA, BSP_IO_PORT_06_PIN_01}, /* 9 R_shoulder */
    {5U, GPT_IO_PIN_GTIOCB, BSP_IO_PORT_06_PIN_00}, /* 10 R_elbow */
    {6U, GPT_IO_PIN_GTIOCA, BSP_IO_PORT_03_PIN_04}, /* 11 R_wrist_pitch */
    {6U, GPT_IO_PIN_GTIOCB, BSP_IO_PORT_03_PIN_03}, /* 12 R_wrist_yaw */
    {2U, GPT_IO_PIN_GTIOCA, BSP_IO_PORT_01_PIN_11}  /* 13 base_slide */
};
static timer_cfg_t s_timer_cfg[TIMER_COUNT];
static gpt_extended_cfg_t s_timer_extend[TIMER_COUNT];
static uint32_t s_period[TIMER_COUNT];
static uint16_t s_enabled;
static uint16_t s_pending;
static uint32_t s_pending_since[AP_JOINTS];
static bool s_hardware_ready;
static ap_player_t s_player;
static ap_frame_t s_manual_pose;
static uint32_t s_owner = 1U;
static bool s_show_running;
static uint32_t s_show_next;
static uint32_t s_show_due;
static bool s_returning_home;
static bool s_fault_reported;

typedef struct
{
    sci_uart_instance_ctrl_t * ctrl;
    uart_cfg_t cfg;
    bool opened;
    volatile uint16_t rx_head;
    volatile uint16_t rx_tail;
    volatile bool rx_fault;
    volatile bool rx_discard;
    uint8_t rx[RX_SIZE];
    volatile bool tx_done;
    uint16_t tx_head;
    uint16_t tx_tail;
    uint8_t tx[TX_SIZE];
    uint8_t tx_chunk[128];
    char line[LINE_SIZE];
    uint32_t used;
    bool line_discard;
} app_port_t;
static app_port_t s_ports[PORT_COUNT]; /* 0 SCI2/PYNQ, 1 SCI7/PC */

void SysTick_Handler(void)
{
    ++g_app_ms;
}

static bool driver_ok(fsp_err_t err)
{
    if (err != FSP_SUCCESS) { g_servo_error = err; return false; }
    return true;
}

static uint32_t counts(uint32_t timer, uint32_t pulse_us)
{
    return (uint32_t) (((uint64_t) s_period[timer] * pulse_us + PERIOD_US / 2U) / PERIOD_US);
}

static bool hardware_init(void)
{
    bool pins_ok = true;
    for (uint32_t j = 0U; j < AP_JOINTS; ++j)
    {
        if (!driver_ok(R_IOPORT_PinCfg(&g_ioport_ctrl, s_joint[j].pin,
            (uint32_t) IOPORT_CFG_PORT_DIRECTION_OUTPUT |
            (uint32_t) IOPORT_CFG_PORT_OUTPUT_LOW))) { pins_ok = false; }
    }
    if (!pins_ok) { return false; }
    for (uint32_t t = 0U; t < TIMER_COUNT; ++t)
    {
        s_timer_cfg[t] = *s_timers[t]->p_cfg;
        s_timer_extend[t] = *(const gpt_extended_cfg_t *) s_timer_cfg[t].p_extend;
        s_timer_extend[t].gtioca.output_enabled = true;
        /* GPT3 B is not used: P112 belongs to UART. */
        s_timer_extend[t].gtiocb.output_enabled = (s_timer_cfg[t].channel != 3U);
        s_timer_extend[t].gtioca.stop_level = GPT_PIN_LEVEL_LOW;
        s_timer_extend[t].gtiocb.stop_level = GPT_PIN_LEVEL_LOW;
        s_timer_extend[t].gtior_setting.gtior = 0U;
        s_timer_cfg[t].p_extend = &s_timer_extend[t];
        s_period[t] = s_timer_cfg[t].period_counts;
        s_timer_cfg[t].duty_cycle_counts = counts(t, AP_BASE_STOP_US);
        if (s_timer_cfg[t].mode != TIMER_MODE_PWM)
        { g_servo_error = FSP_ERR_INVALID_MODE; return false; }
        if (!driver_ok(R_GPT_Open(s_timers[t]->p_ctrl, &s_timer_cfg[t]))) { return false; }
        timer_info_t info = {0};
        if (!driver_ok(R_GPT_InfoGet(s_timers[t]->p_ctrl, &info))) { return false; }
        if ((info.period_counts == 0U) || (info.clock_frequency == 0U) ||
            (info.count_direction != TIMER_DIRECTION_UP) ||
            (((uint64_t) info.period_counts * 1000000U / info.clock_frequency) != PERIOD_US))
        {
            g_servo_error = FSP_ERR_INVALID_ARGUMENT;
            return false;
        }
        s_period[t] = info.period_counts;
        if (!driver_ok(R_GPT_Start(s_timers[t]->p_ctrl))) { return false; }
    }
    /* Timers run internally; all 13 physical signal pins remain GPIO low. */
    return true;
}

static bool hardware_write(uint32_t joint, uint16_t pulse_us, bool first)
{
    if (!s_hardware_ready || !ap_pulse_valid(joint, pulse_us)) { return false; }
    const joint_pin_t * pin = &s_joint[joint];
    if (!driver_ok(R_GPT_DutyCycleSet(s_timers[pin->timer]->p_ctrl,
        counts(pin->timer, pulse_us), (uint32_t) pin->output))) { return false; }
    if (first)
    {
        s_pending |= (uint16_t) (1U << joint);
        s_pending_since[joint] = g_app_ms;
    }
    return true;
}

static int hardware_ready(void)
{
    for (uint32_t j = 0U; j < AP_JOINTS; ++j)
    {
        uint16_t bit = (uint16_t) (1U << j);
        if (((s_pending & bit) == 0U) ||
            ((uint32_t) (g_app_ms - s_pending_since[j]) < 25U)) { continue; }
        uint32_t t = s_joint[j].timer;
        timer_status_t status = {0};
        if (!driver_ok(R_GPT_StatusGet(s_timers[t]->p_ctrl, &status))) { return -1; }
        if (status.state != TIMER_STATE_COUNTING)
        { g_servo_error = FSP_ERR_INVALID_STATE; return -1; }
        /* Let buffered duty transfer, then mux during the LOW phase. */
        if ((status.counter < counts(t, 3000U)) ||
            (status.counter > counts(t, 18000U))) { continue; }
        if (!driver_ok(R_IOPORT_PinCfg(&g_ioport_ctrl, s_joint[j].pin,
            (uint32_t) IOPORT_CFG_PERIPHERAL_PIN |
            (uint32_t) IOPORT_PERIPHERAL_GPT1))) { return -1; }
        s_enabled |= bit;
        s_pending &= (uint16_t) ~bit;
    }
    return (s_pending == 0U) ? 1 : 0;
}

static uint16_t hardware_cancel_pending(void)
{
    s_pending = 0U;
    return s_enabled;
}

static void app_uart_callback(uart_callback_args_t * args)
{
    app_port_t * port = (app_port_t *) args->p_context;
    if (port == NULL) { return; }
    if (args->event == UART_EVENT_TX_COMPLETE) { port->tx_done = true; }
    else if (args->event == UART_EVENT_RX_CHAR)
    {
        uint8_t value = (uint8_t) args->data;
        if (port->rx_discard)
        {
            if ((value == '\n') || (value == '\r')) { port->rx_discard = false; }
            return;
        }
        uint16_t next = (uint16_t) ((port->rx_head + 1U) % RX_SIZE);
        if (next == port->rx_tail)
        {
            port->rx_fault = true;
            port->rx_discard = true;
        }
        else
        {
            port->rx[port->rx_head] = value;
            __DMB();
            port->rx_head = next;
        }
    }
    else if ((args->event == UART_EVENT_ERR_PARITY) ||
             (args->event == UART_EVENT_ERR_FRAMING) ||
             (args->event == UART_EVENT_ERR_OVERFLOW) ||
             (args->event == UART_EVENT_BREAK_DETECT))
    {
        port->rx_fault = true;
        port->rx_discard = true;
    }
}

/* The old uart6_callback stays in ra6m5_echo_reference.c. A copied SCI2
 * configuration selects app_uart_callback without changing generated files.
 */
void uart7_callback(uart_callback_args_t * p_args)
{
    app_uart_callback(p_args);
}

static void uart_init(void)
{
    s_ports[0].ctrl = &g_uart6_ctrl;
    s_ports[0].cfg = g_uart6_cfg;
    s_ports[1].ctrl = &g_uart7_ctrl;
    s_ports[1].cfg = g_uart7_cfg;
    for (uint32_t p = 0U; p < PORT_COUNT; ++p)
    {
        s_ports[p].cfg.p_context = &s_ports[p];
        s_ports[p].cfg.p_callback = app_uart_callback;
        s_ports[p].tx_done = true;
        g_uart_error[p] = R_SCI_UART_Open(s_ports[p].ctrl, &s_ports[p].cfg);
        s_ports[p].opened = (g_uart_error[p] == FSP_SUCCESS);
    }
}

static void reply(uint32_t p, const char * text)
{
    app_port_t * port = &s_ports[p];
    size_t length = strlen(text);
    if (!port->opened) { return; }
    uint32_t free_bytes = (port->tx_tail + TX_SIZE - port->tx_head - 1U) % TX_SIZE;
    if (length > free_bytes) { ++g_uart_tx_dropped[p]; return; }
    for (size_t i = 0U; i < length; ++i)
    {
        port->tx[port->tx_head] = (uint8_t) text[i];
        port->tx_head = (uint16_t) ((port->tx_head + 1U) % TX_SIZE);
    }
}

static void uart_tx_service(uint32_t p)
{
    app_port_t * port = &s_ports[p];
    if (!port->opened || !port->tx_done || (port->tx_head == port->tx_tail)) { return; }
    uint16_t tail = port->tx_tail;
    uint32_t count = 0U;
    while ((tail != port->tx_head) && (count < sizeof(port->tx_chunk)))
    {
        port->tx_chunk[count++] = port->tx[tail];
        tail = (uint16_t) ((tail + 1U) % TX_SIZE);
    }
    port->tx_done = false;
    g_uart_error[p] = R_SCI_UART_Write(port->ctrl, port->tx_chunk, count);
    if (g_uart_error[p] == FSP_SUCCESS) { port->tx_tail = tail; }
    else { port->tx_done = true; }
}

static void state_publish(void)
{
    g_show_running = s_show_running ? 1U : 0U;
    g_servo_enabled_mask = s_enabled;
    g_action_frame = (s_player.count == 0U) ? 0U :
        ((s_player.frame < s_player.count) ? s_player.frame + 1U : s_player.count);
    g_servo_stage = !s_hardware_ready || (s_player.state == AP_FAULT) ? 99U :
        ((s_player.state == AP_ARMING) ? 15U : ((s_player.state == AP_MOVING) ? 20U : 10U));
    for (uint32_t j = 0U; j < AP_JOINTS; ++j)
    {
        g_servo_applied_us[j] = ((s_enabled & (1U << j)) != 0U) ? s_player.pulse[j] : 0U;
    }
}

static void status_reply(uint32_t p)
{
    char message[256];
    state_publish();
    (void) snprintf(message, sizeof(message),
        "STATUS stage=%lu frame=%lu enabled=0x%04lX servo_err=%lu uart_err=%lu rx_err=%lu tx_drop=%lu\r\n",
        (unsigned long) g_servo_stage, (unsigned long) g_action_frame,
        (unsigned long) g_servo_enabled_mask, (unsigned long) g_servo_error,
        (unsigned long) g_uart_error[p], (unsigned long) g_uart_rx_errors[p],
        (unsigned long) g_uart_tx_dropped[p]);
    reply(p, message);
    (void) snprintf(message, sizeof(message), "GROUP %lu SHOW %lu HOME %lu\r\n",
        (unsigned long) g_action_group, (unsigned long) g_show_running,
        (unsigned long) (s_returning_home ? 1U : 0U));
    reply(p, message);
    for (uint32_t j = 0U; j < AP_JOINTS; ++j)
    {
        (void) snprintf(message, sizeof(message), "%s%u",
            (j == 0U) ? "PULSE " : " ", (unsigned int) g_servo_applied_us[j]);
        reply(p, message);
    }
    reply(p, "\r\n");
}

static void start_command(uint32_t p, const ap_command_t * command)
{
    if (!s_hardware_ready || (s_player.state == AP_FAULT)) { reply(p, "ERR FAULT\r\n"); return; }
    if (s_show_running || (s_player.state != AP_IDLE)) { reply(p, "ERR BUSY\r\n"); return; }
    ap_result_t result;
    s_show_running = false; /* Manual actions are allowed only while the continuous loop is stopped. */
    if (command->kind == CMD_ACTION)
    {
        if ((command->group_id < 1U) || (command->group_id > ACTION_GROUP_COUNT))
        { reply(p, "ERR GROUP\r\n"); return; }
        const action_group_t * group = &g_action_groups[command->group_id - 1U];
        result = ap_start(&s_player, group->frames, group->count, g_app_ms);
        g_action_group = command->group_id;
    }
    else
    {
        s_manual_pose = command->pose;
        result = ap_start(&s_player, &s_manual_pose, 1U, g_app_ms);
        g_action_group = 0U;
    }
    if (result == AP_OK)
    {
        s_owner = p;
        char message[32];
        if (command->kind == CMD_ACTION)
        {
            (void) snprintf(message, sizeof(message), "OK ACT%02lu\r\n", (unsigned long) command->group_id);
            reply(p, message);
        }
        else { reply(p, "OK POSE\r\n"); }
    }
    else { reply(p, (result == AP_IO_ERROR) ? "ERR FAULT\r\n" : "ERR RANGE\r\n"); }
}

static ap_result_t return_to_home(uint32_t owner)
{
    s_show_running = false;
    s_show_next = 1U;
    s_owner = owner;
    ap_result_t result = ap_stop(&s_player); /* Stop base immediately; cancel current frame. */
    if (result != AP_OK) { s_returning_home = false; return result; }
    s_manual_pose = g_boot_home[0]; /* Preserve the already calibrated home and all action data. */
    s_manual_pose.duration_ms = ROBOT_RETURN_HOME_MS;
    s_manual_pose.base_run_ms = 0U;
    g_action_group = 0U;
    result = ap_start(&s_player, &s_manual_pose, 1U, g_app_ms);
    s_returning_home = (result == AP_OK);
    return result;
}

static void show_schedule(uint32_t owner, uint32_t delay_ms)
{
    s_owner = owner;
    s_show_next = 1U; /* START begins ACT01; never replay the old boot hold between cycles. */
    s_show_due = g_app_ms + delay_ms;
    s_show_running = true;
}

static void show_service(void)
{
    if (!s_show_running || s_returning_home || (s_player.state != AP_IDLE) ||
        ((int32_t) (g_app_ms - s_show_due) < 0)) { return; }
    const action_group_t * group = &g_action_groups[s_show_next - 1U];
    g_action_group = s_show_next;
    ap_result_t result = ap_start(&s_player, group->frames, group->count, g_app_ms);
    if (result == AP_OK)
    {
        s_show_next = (s_show_next >= ACTION_GROUP_COUNT) ? 1U : s_show_next + 1U;
        char message[32];
        (void) snprintf(message, sizeof(message), "RUN GROUP %lu\r\n", (unsigned long) g_action_group);
        reply(s_owner, message);
    }
    else { s_show_running = false; reply(s_owner, "ERR SHOW\r\n"); }
}

static void handle_command(uint32_t p, const char * line)
{
    ap_command_t command;
    if (!ap_parse(line, &command)) { reply(p, "ERR COMMAND\r\n"); return; }
    switch (command.kind)
    {
        case CMD_PING: reply(p, "PONG\r\n"); break;
        case CMD_STATUS: status_reply(p); break;
        case CMD_SHOW:
            if (!s_hardware_ready || (s_player.state == AP_FAULT)) { reply(p, "ERR FAULT\r\n"); }
            else if (s_show_running) { reply(p, "OK START\r\n"); } /* Repeated START is idempotent. */
            else
            {
                /* A START during home return is queued until home completes. */
                if (!s_returning_home && (s_player.state != AP_IDLE))
                {
                    if (ap_stop(&s_player) != AP_OK) { reply(p, "ERR FAULT\r\n"); break; }
                }
                show_schedule(p, 0U);
                reply(p, "OK START\r\n");
            }
            break;
        case CMD_STOP:
        {
            s_show_running = false; /* Cancel the loop and any queued START before returning home. */
            if (s_returning_home)
            {
                s_owner = p;
                reply(p, "OK STOP\r\n"); /* Do not restart interpolation on repeated STOP. */
                break;
            }
            ap_result_t result = return_to_home(p);
            reply(p, (result == AP_OK) ? "OK STOP\r\n" : "ERR FAULT\r\n");
            break;
        }
        default: start_command(p, &command); break;
    }
}

static void uart_rx_service(uint32_t p)
{
    app_port_t * port = &s_ports[p];
    if (!port->opened) { return; }
    uint32_t irq_state = __get_PRIMASK();
    __disable_irq();
    bool damaged = port->rx_fault;
    if (damaged)
    {
        port->rx_tail = port->rx_head;
        port->rx_fault = false;
        port->rx_discard = true;
        port->used = 0U;
        port->line_discard = false;
    }
    __set_PRIMASK(irq_state);
    if (damaged)
    {
        ++g_uart_rx_errors[p];
        if (ROBOT_STOP_ON_RX_ERROR != 0U)
        {
            s_show_running = false;
            s_returning_home = false;
            (void) ap_stop(&s_player);
        }
        reply(p, "ERR RX; SEND NEWLINE THEN RETRY\r\n");
    }
    for (uint32_t budget = 0U; (budget < 64U) && (port->rx_tail != port->rx_head); ++budget)
    {
        uint8_t value = port->rx[port->rx_tail];
        __DMB();
        port->rx_tail = (uint16_t) ((port->rx_tail + 1U) % RX_SIZE);
        if (port->rx_fault) { break; }
        if ((value == '\r') || (value == '\n'))
        {
            if (port->line_discard) { reply(p, "ERR LINE\r\n"); }
            else if (port->used != 0U)
            {
                port->line[port->used] = '\0';
                handle_command(p, port->line);
            }
            port->used = 0U;
            port->line_discard = false;
        }
        else if (((value < 32U) && (value != '\t')) || (value > 126U) ||
                 (port->used >= LINE_SIZE - 1U))
        {
            port->line_discard = true;
        }
        else if (!port->line_discard) { port->line[port->used++] = (char) value; }
    }
}

static void playback_service(void)
{
    show_service();
    ap_result_t result = ap_tick(&s_player, g_app_ms);
    if (result == AP_DONE)
    {
        if (s_returning_home)
        {
            s_returning_home = false;
            reply(s_owner, "HOME READY\r\n");
            if (s_show_running) { s_show_due = g_app_ms; }
        }
        else if (s_show_running) { s_show_due = g_app_ms + ROBOT_GROUP_GAP_MS; }
        else { reply(s_owner, "DONE\r\n"); }
    }
    else if ((result == AP_IO_ERROR) && !s_fault_reported)
    {
        if (g_servo_error == FSP_SUCCESS) { g_servo_error = FSP_ERR_TIMEOUT; }
        reply(s_owner, "ERR FAULT; STATUS\r\n");
        s_show_running = false;
        s_returning_home = false;
        s_fault_reported = true;
    }
}

void hal_entry(void)
{
    const ap_io_t io = {hardware_write, hardware_ready, hardware_cancel_pending};
    ap_init(&s_player, &io);
    s_hardware_ready = hardware_init();
    uint32_t clock_hz = R_FSP_SystemClockHzGet(FSP_PRIV_CLOCK_ICLK);
    if ((clock_hz < 1000U) || (SysTick_Config(clock_hz / 1000U) != 0U))
    {
        g_servo_error = FSP_ERR_INVALID_ARGUMENT;
        s_hardware_ready = false;
    }
    uart_init();
    for (uint32_t p = 0U; p < PORT_COUNT; ++p)
    {
        reply(p, s_hardware_ready ? "READY SERVO13 PYNQ; START LOOP / STOP HOME / STATUS\r\n" : "ERR INIT; STATUS\r\n");
    }
    /* Power on at home and hold indefinitely. Only a received START requests the loop. */
    if (s_hardware_ready && (return_to_home(0U) != AP_OK))
    { reply(0U, "ERR HOME; STATUS\r\n"); }
    while (1)
    {
        for (uint32_t p = 0U; p < PORT_COUNT; ++p) { uart_rx_service(p); }
        uint32_t command = g_action_command;
        if (command != 0U)
        {
            g_action_command = 0U;
            if (command == 1U)
            {
                ap_command_t request = {0};
                request.kind = CMD_ACTION;
                request.group_id = g_action_select;
                start_command(1U, &request);
            }
            else if (command == 2U) { handle_command(1U, "STOP"); }
            else if (command == 3U) { handle_command(1U, "START"); }
            else { reply(1U, "ERR DEBUG COMMAND\r\n"); }
        }
        if (s_hardware_ready)
        {
            playback_service();
        }
        state_publish();
        for (uint32_t p = 0U; p < PORT_COUNT; ++p) { uart_tx_service(p); }
        R_BSP_SoftwareDelay(1U, BSP_DELAY_UNITS_MILLISECONDS);
    }
}

void R_BSP_WarmStart(bsp_warm_start_event_t event)
{
    if (BSP_WARM_START_RESET == event)
    {
#if BSP_FEATURE_FLASH_LP_VERSION != 0
        R_FACI_LP->DFLCTL = 1U;
#endif
    }
    if (BSP_WARM_START_POST_C == event)
    {
        R_IOPORT_Open(&g_ioport_ctrl, &IOPORT_CFG_NAME);
    }
}

#if BSP_TZ_SECURE_BUILD
FSP_CPP_HEADER
BSP_CMSE_NONSECURE_ENTRY void template_nonsecure_callable(void);
void template_nonsecure_callable(void) { }
FSP_CPP_FOOTER
#endif
