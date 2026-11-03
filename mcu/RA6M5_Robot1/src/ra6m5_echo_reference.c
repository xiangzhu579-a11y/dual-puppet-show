/*
 * Reference logic for an existing Renesas FSP project.
 * Integrate this behavior with SCI6 (g_uart6); do not copy generated FSP files.
 * UART: 115200, 8N1, no hardware flow control.
 */

#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include "hal_data.h"
void ra6m5_uart_echo_test(void);
static volatile bool rx_done = false;
static volatile bool tx_done = false;

void uart6_callback(uart_callback_args_t * p_args)
{
    if (UART_EVENT_RX_COMPLETE == p_args->event)
    {
        rx_done = true;
    }
    else if (UART_EVENT_TX_COMPLETE == p_args->event)
    {
        tx_done = true;
    }
}

static void uart6_write_blocking(uint8_t const * data, uint32_t length)
{
    tx_done = false;
    (void) R_SCI_UART_Write(&g_uart6_ctrl, data, length);
    while (!tx_done)
    {
        /* Test-only blocking wait. */
    }
}

void ra6m5_uart_echo_test(void)
{
    uint8_t byte;
    uint8_t line[64];
    uint32_t used = 0;
    static uint8_t const pong[] = "PONG\r\n";

    (void) R_SCI_UART_Open(&g_uart6_ctrl, &g_uart6_cfg);

    while (1)
    {
        rx_done = false;
        (void) R_SCI_UART_Read(&g_uart6_ctrl, &byte, 1);
        while (!rx_done)
        {
            /* Test-only blocking wait. */
        }

        if (used < sizeof(line))
        {
            line[used++] = byte;
        }
        else
        {
            used = 0;
        }

        if ('\n' == byte)
        {
            if ((6U == used) && (0 == memcmp(line, "PING\r\n", 6U)))
            {
                uart6_write_blocking(pong, sizeof(pong) - 1U);
            }
            else
            {
                uart6_write_blocking(line, used);  /* Echo other complete lines. */
            }
            used = 0;
        }
    }
}

