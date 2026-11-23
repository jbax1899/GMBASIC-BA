//draw system background
draw_set_color(back_color);
draw_rectangle(0, 0, room_width, room_height, false);

if (!surface_exists(back_buffer))
{
    back_buffer = surface_create(800, 600);
    program.graphics_dirty = true;
}

// A redraw starts with the color left by the previous frame.
if (program.graphics_dirty || graphics_program != program || graphics_render_color != graphics_color)
{
    graphics_program = program;
    graphics_render_color = graphics_color;
    program.graphics_dirty = false;

    var _old_world = matrix_get(matrix_world);
    var _old_view = matrix_get(matrix_view);
    var _old_proj = matrix_get(matrix_projection);

    surface_set_target(back_buffer);
    draw_clear_alpha(c_black, 1);

    var _graphics = objSystem.program.graphics;
    var _len = array_length(_graphics);

    for (var _i = 0; _i < _len; _i++)
    {
        var _item = _graphics[_i];
        
        if (_item.kind == "MATRIXSETWORLD")
        {
            matrix_set(matrix_world, _item.matrix);
        }
        if (_item.kind == "MATRIXSETPROJ")
        {
            matrix_set(matrix_projection, _item.matrix);
        }
        if (_item.kind == "MATRIXSETVIEW")
        {
            matrix_set(matrix_view, _item.matrix);
        }
        if (_item.kind == "LINE")
        {
            draw_line_color(_item.x1, _item.y1, _item.x2, _item.y2, graphics_color, graphics_color);
        }
        else if (_item.kind == "TRI")
        {
            draw_triangle_color(_item.x1, _item.y1, _item.x2, _item.y2,_item.x3, _item.y3, graphics_color, graphics_color, graphics_color, true);
        }
        else if (_item.kind == "FTRI")
        {
            draw_triangle_color(_item.x1, _item.y1, _item.x2, _item.y2,_item.x3, _item.y3, graphics_color, graphics_color, graphics_color, false);
        }
        else if (_item.kind == "RECT")
        {
            draw_rectangle_color(_item.x1, _item.y1, _item.x2, _item.y2, graphics_color, graphics_color, graphics_color, graphics_color, true);
        }
        else if (_item.kind == "CIRC")
        {
            draw_circle_color(_item.x1, _item.y1, _item.x2,
                graphics_color, graphics_color, true);
        }
        else if (_item.kind == "FCIRC")
        {
            draw_circle_color(_item.x1, _item.y1, _item.x2,
                graphics_color, graphics_color, false);
        }
        else if (_item.kind == "FRECT")
        {
            draw_rectangle_color(_item.x1, _item.y1, _item.x2, _item.y2,
                graphics_color, graphics_color, graphics_color, graphics_color, false);
        }
        else if (_item.kind == "SETDRAWCOLOR")
        {
            graphics_color = _item.col;
        }
        else if (_item.kind == "DRAWSPRITE")
        {
            draw_sprite_ext(_item.sprite, _item.frame, _item.x, _item.y, 1, 1, 0, graphics_color, 1.0);
        }
    }

    surface_reset_target();
    matrix_set(matrix_world, _old_world);
    matrix_set(matrix_view, _old_view);
    matrix_set(matrix_projection, _old_proj);
}

draw_surface(back_buffer, 10, 10);


/// BASIC output shares the graphics area in both rooms.
var _region = application_get_position();
var _scissor = gpu_get_scissor();
var _line_h = 24;
var _count, _first;
draw_set_halign(fa_left);
draw_set_color(text_color);

if (output_source != program.output)
{
    output_source = program.output;
    output_rows = [];
    var _text = string_replace_all(string_replace_all(output_source, "\r\n", "\n"), "\r", "\n");
    var _line = "";
    var _length = string_length(_text);
    for (var _i = 1; _i <= _length; _i++)
    {
        var _char = string_char_at(_text, _i);
        // Hard-wrap long words and restart the row on an explicit newline.
        if (_char == "\n" || string_width(_line + _char) > 800)
        {
            array_push(output_rows, _line);
            _line = "";
        }
        if (_char != "\n") _line += _char;
    }
    array_push(output_rows, _line);
}

if (output_source != "")
{
    editor_pane_scissor(_region, 10, 10, 810, 610);
    _count = array_length(output_rows);
    _first = max(0, _count - (600 div _line_h));
    for (var _i = _first; _i < _count; _i++)
    {
        draw_text(10, 10 + (_i - _first) * _line_h, output_rows[_i]);
    }
    gpu_set_scissor(_scissor);
}

if (room == rmConsole)
{
    var _display_text = typed_text;
    if(on)
    {
        _display_text = string_insert(cursor, _display_text, position);
    }
    editor_pane_scissor(_region, 10, room_height - 36, row_length + 15, room_height);
    draw_text(10, room_height - 36, ">" + _display_text);
    gpu_set_scissor(_scissor);

    ///PROGRAM PANE
    var _pane_left = row_length + 20;
    var _pane_top = 10;
    var _pane_height = 600;

    editor_pane_scissor(_region, _pane_left, _pane_top, room_width, _pane_top + _pane_height);

    if(program.loaded)
    {
        var _highlight = show_highlight ? program_line_index(program.current_line) : -1;
        var _line_count = array_length(program.lines);
        var _first_line = max(0, floor(program_scroll_y / _line_h));
        var _last_line = min(_line_count - 1, ceil((program_scroll_y + _pane_height) / _line_h) - 1);

        for (var _i = _first_line; _i <= _last_line; _i++)
        {
            var _y = _pane_top + (_i * _line_h) - program_scroll_y;

            if (_i == _highlight)
            {
                draw_set_color(c_white - text_color);
                draw_rectangle(_pane_left, _y, room_width, _y + _line_h, false);
            }

            draw_set_color(text_color);
            var _line = string_copy(program.lines[_i], 1, 150);
            draw_text(_pane_left, _y, string_replace_all(string_replace_all(_line, "\r", ""), "\n", " "));
        }
    }

    gpu_set_scissor(_scissor);

    ///VARIABLES PANE
    _pane_left = row_length + 20;
    _pane_top = 615;
    _pane_height = room_height - _pane_top - _line_h;

    var _names = variable_struct_get_names(program.variables);
    _count = array_length(_names);

    _first = max(0, floor(variables_scroll_y / _line_h));
    var _last = min(_count - 1, ceil((variables_scroll_y + _pane_height) / _line_h) - 1);
    draw_text(_pane_left, _pane_top, "VARIABLES:");
    editor_pane_scissor(_region, _pane_left, _pane_top + _line_h, room_width, room_height);

    for (var _i = _first; _i <= _last; _i++)
    {
        var _y = _pane_top + _line_h + (_i * _line_h) - variables_scroll_y;

        var _name = _names[_i];
        var _value = variable_struct_get(program.variables, _name);

        draw_text(_pane_left, _y, _name + ": " + string_replace_all(string_replace_all(string(_value), "\r", ""), "\n", " "));
    }

    gpu_set_scissor(_scissor);

    ///ERRORS PANE
    _pane_left = 10;
    _pane_top = 615;
    _pane_height = room_height - _pane_top - _line_h - 36;

    _count = array_length(program.errors);

    _first = max(0, floor(errors_scroll_y / _line_h));
    _last = min(_count - 1, ceil((errors_scroll_y + _pane_height) / _line_h) - 1);
    draw_text(_pane_left, _pane_top, "CONSOLE:");
    editor_pane_scissor(_region, _pane_left, _pane_top + _line_h, row_length + 15, room_height - 36);

    for (var _i = _first; _i <= _last; _i++)
    {
        var _y = _pane_top + _line_h + (_i * _line_h) - errors_scroll_y;

        draw_text(_pane_left, _y, string_replace_all(string_replace_all(program.errors[_i], "\r", ""), "\n", " "));
    }

    gpu_set_scissor(_scissor);

    draw_line_width_colour(row_length + 15, 0, row_length + 15, room_height, 4, text_color, text_color);
    draw_line_width_colour(0, 610, room_width, 610, 4, text_color, text_color);
}
