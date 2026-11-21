-- Flattens a Hyprland Lua config into canonical one-line statements.
--
-- Usage: lua flatten_hypr.lua /path/to/hyprland.lua [module-to-skip]
--
-- The config is executed against a stub `hl` table that records every call.
-- Locals, loops and string concatenation are therefore resolved, and the
-- output is a list of self-contained statements in the same syntax the model
-- is trained to write, e.g.
--   hl.config({ general = { gaps_in = 5 } })
--   hl.bind("SUPER + Q", hl.dsp.exec_cmd("kitty"))
-- Nothing here talks to a running compositor.

local path, skip_module = arg[1], arg[2]
if not path then
  io.stderr:write("usage: flatten_hypr.lua CONFIG [MODULE_TO_SKIP]\n")
  os.exit(2)
end

local dir = path:match("^(.*)/[^/]*$") or "."
package.path = dir .. "/?.lua;" .. dir .. "/?/init.lua;" .. package.path

local out = {}
local function emit(s) out[#out + 1] = s end

---------------------------------------------------------------- serialiser
local ser

local function is_ident(s)
  return type(s) == "string" and s:match("^[%a_][%w_]*$") ~= nil
end

local function quote(s)
  return '"' .. s:gsub('\\', '\\\\'):gsub('"', '\\"'):gsub('\n', '\\n') .. '"'
end

local function is_array(t)
  local n = 0
  for _ in pairs(t) do n = n + 1 end
  for i = 1, n do if t[i] == nil then return false end end
  return true, n
end

ser = function(v)
  local tv = type(v)
  if tv == "string" then return quote(v) end
  if tv == "number" then
    if math.type(v) == "integer" then
      if v > 0xFFFFFF then return string.format("0x%08x", v) end
      return tostring(v)
    end
    local s = string.format("%.6g", v)
    return s
  end
  if tv == "boolean" or tv == "nil" then return tostring(v) end
  if tv == "function" then return "function() --[[...]] end" end
  if tv == "table" then
    local mt = getmetatable(v)
    if mt and mt.__repr then return mt.__repr(v) end
    local arr, n = is_array(v)
    if arr then
      if n == 0 then return "{}" end
      local parts = {}
      for i = 1, n do parts[i] = ser(v[i]) end
      return "{ " .. table.concat(parts, ", ") .. " }"
    end
    local keys = {}
    for k in pairs(v) do keys[#keys + 1] = k end
    table.sort(keys, function(a, b) return tostring(a) < tostring(b) end)
    local parts = {}
    for _, k in ipairs(keys) do
      local ks = is_ident(k) and k or ("[" .. ser(k) .. "]")
      parts[#parts + 1] = ks .. " = " .. ser(v[k])
    end
    return "{ " .. table.concat(parts, ", ") .. " }"
  end
  return "nil"
end

---------------------------------------------------------------- handles
-- Objects returned by hl.bind, hl.window_rule, ... accept any method call.
local function handle()
  return setmetatable({}, {
    __index = function() return function() return nil end end,
    __repr = function() return "nil" end,
  })
end

---------------------------------------------------------------- dispatchers
local function dispatcher(name)
  return function(...)
    local args = table.pack(...)
    local parts = {}
    for i = 1, args.n do parts[i] = ser(args[i]) end
    return setmetatable({ __dsp = name }, {
      __repr = function() return "hl.dsp." .. name .. "(" .. table.concat(parts, ", ") .. ")" end,
    })
  end
end

local function dsp_namespace(prefix)
  return setmetatable({}, {
    __index = function(t, k)
      local full = prefix and (prefix .. "." .. k) or k
      local v
      if not prefix and (k == "window" or k == "workspace" or k == "group" or k == "cursor") then
        v = dsp_namespace(k)
      else
        v = dispatcher(full)
      end
      rawset(t, k, v)
      return v
    end,
  })
end

---------------------------------------------------------------- config
-- Value-shaped tables that must not be flattened further.
local function is_value_table(t)
  if type(t) ~= "table" or getmetatable(t) then return true end
  if next(t) == nil then return true end
  if is_array(t) then return true end
  for k in pairs(t) do
    if not (k == "colors" or k == "angle" or k == "top" or k == "right"
            or k == "bottom" or k == "left") then
      return false
    end
  end
  return true
end

local function nest(pathstr, value)
  local segs = {}
  for seg in pathstr:gmatch("[^%.]+") do segs[#segs + 1] = seg end
  local s = ser(value)
  for i = #segs, 1, -1 do
    local k = is_ident(segs[i]) and segs[i] or ("[" .. quote(segs[i]) .. "]")
    s = "{ " .. k .. " = " .. s .. " }"
  end
  return "hl.config(" .. s .. ")"
end

local config_values, config_order = {}, {}
local function set_config(p, v)
  if config_values[p] == nil then config_order[#config_order + 1] = p end
  config_values[p] = v
end

local function sorted_pairs(t)
  local keys = {}
  for k in pairs(t) do keys[#keys + 1] = k end
  table.sort(keys, function(a, b) return tostring(a) < tostring(b) end)
  local i = 0
  return function()
    i = i + 1
    local k = keys[i]
    if k ~= nil then return k, t[k] end
  end
end

local function walk(prefix, t)
  for k, v in sorted_pairs(t) do
    local p = prefix and (prefix .. "." .. k) or tostring(k)
    if type(v) == "table" and not is_value_table(v) then
      walk(p, v)
    else
      set_config(p, v)
    end
  end
end

---------------------------------------------------------------- binds
local binds, bind_order = {}, {}
local current_submap = nil

local function bind_key(keys)
  return (keys:gsub("%s+", " "):gsub("^%s+", ""):gsub("%s+$", ""))
end

local function record_bind(keys, d, opts)
  local key = bind_key(keys)
  local s = "hl.bind(" .. quote(key) .. ", " .. ser(d)
  if opts ~= nil and next(opts) ~= nil then s = s .. ", " .. ser(opts) end
  s = s .. ")"
  if current_submap then s = s .. " -- submap " .. current_submap end
  local id = (current_submap or "") .. "\0" .. key
  if binds[id] == nil then bind_order[#bind_order + 1] = id end
  binds[id] = binds[id] or {}
  table.insert(binds[id], s)
  return handle()
end

---------------------------------------------------------------- the stub
local events = {}
local generic = {}

local function call_line(name)
  return function(...)
    local args = table.pack(...)
    local parts = {}
    for i = 1, args.n do parts[i] = ser(args[i]) end
    generic[#generic + 1] = "hl." .. name .. "(" .. table.concat(parts, ", ") .. ")"
    return handle()
  end
end

local exec_sink = nil

hl = setmetatable({
  config = function(t)
    for k, v in sorted_pairs(t) do
      if type(v) == "table" and not is_value_table(v) then
        walk(tostring(k), v)
      else
        set_config(tostring(k), v)
      end
    end
  end,
  bind = record_bind,
  unbind = function(keys)
    local key = bind_key(keys)
    binds[(current_submap or "") .. "\0" .. key] = nil
  end,
  dsp = dsp_namespace(nil),
  exec_cmd = function(cmd, rules)
    local s = "hl.exec_cmd(" .. quote(cmd) .. (rules and (", " .. ser(rules)) or "") .. ")"
    if exec_sink then exec_sink[#exec_sink + 1] = s else generic[#generic + 1] = s end
  end,
  on = function(event, fn)
    if event == "hyprland.start" and type(fn) == "function" then
      local sink = {}
      exec_sink = sink
      local ok = pcall(fn)
      exec_sink = nil
      for _, s in ipairs(sink) do
        events[#events + 1] = 'hl.on("hyprland.start", function() ' .. s .. ' end)'
      end
      if not ok or #sink == 0 then
        events[#events + 1] = 'hl.on("hyprland.start", function() --[[...]] end)'
      end
    else
      events[#events + 1] = "hl.on(" .. quote(tostring(event)) .. ", function() --[[...]] end)"
    end
    return handle()
  end,
  define_submap = function(name, reset_or_fn, fn)
    local body = type(reset_or_fn) == "function" and reset_or_fn or fn
    generic[#generic + 1] = "hl.define_submap(" .. quote(name) .. ", ...)"
    if type(body) == "function" then
      local prev = current_submap
      current_submap = name
      pcall(body)
      current_submap = prev
    end
  end,
  version = function() return "0.0.0" end,
}, {
  __index = function(t, k)
    if type(k) == "string" and k:match("^get_") then
      return function() return nil end
    end
    if k == "notification" or k == "plugin" or k == "layout" then
      return setmetatable({}, { __index = function() return function() return handle() end end })
    end
    local f = call_line(k)
    rawset(t, k, f)
    return f
  end,
})

-- `require` of the managed module is skipped: the managed file is shown to
-- the model separately.
if skip_module then
  local real_require = require
  require = function(name)
    if name == skip_module then return true end
    return real_require(name)
  end
end

local chunk, err = loadfile(path)
if not chunk then
  io.stderr:write(err .. "\n")
  os.exit(1)
end
local ok, rerr = pcall(chunk)
if not ok then
  io.stderr:write("error while evaluating config: " .. tostring(rerr) .. "\n")
end

---------------------------------------------------------------- output
for _, p in ipairs(config_order) do emit(nest(p, config_values[p])) end
for _, s in ipairs(generic) do emit(s) end
for _, s in ipairs(events) do emit(s) end
for _, id in ipairs(bind_order) do
  if binds[id] then for _, s in ipairs(binds[id]) do emit(s) end end
end

io.write(table.concat(out, "\n"))
if #out > 0 then io.write("\n") end
