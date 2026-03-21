#!/usr/bin/env bun
import { Server } from '@modelcontextprotocol/sdk/server/index.js'
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js'

const mcp = new Server(
  { name: 'cpet-webhook', version: '0.1.0' },
  {
    capabilities: { experimental: { 'claude/channel': {} } },
    instructions: `You are a CPET analysis assistant running on a server.
      Events arrive as <channel source="cpet-webhook" type="new_submission">.
      Content is JSON: {submission_id, job_id, workspace_path, description, files: [{name, extension, size_bytes}]}.
      When you receive this event:
      1. Read the description to understand the test type
      2. Run: python -m pipeline --workspace {workspace_path}
      3. If successful, copy report to published/{slug}/ and update job status
      4. If failed, update job status with error message
      Use the cpet-pipeline skill for detailed instructions.`,
  },
)

await mcp.connect(new StdioServerTransport())

const PORT = parseInt(process.env.CPET_CHANNEL_PORT || '8788')

Bun.serve({
  port: PORT,
  hostname: '127.0.0.1',
  async fetch(req) {
    if (req.method === 'GET' && new URL(req.url).pathname === '/health') {
      return new Response('ok')
    }
    if (req.method !== 'POST') {
      return new Response('method not allowed', { status: 405 })
    }
    const body = await req.text()
    await mcp.notification({
      method: 'notifications/claude/channel',
      params: { content: body, meta: { type: 'new_submission' } },
    })
    return new Response('ok')
  },
})

console.error(`cpet-webhook channel server listening on http://127.0.0.1:${PORT}`)
