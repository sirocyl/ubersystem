
var setVisible = function(selector, visible) {
    $(selector)[visible ? "show" : "hide"]();
}

$.field = function(field) {
    var $field = $("[name=" + field + "]");
    return $field.size() ? $field : null;
};

$.val = function(field) {
    var val = $.field(field).val();
    if ($.field(field).is(":radio")) {
        val = $.field(field).filter(":checked").val();
    }
    return val.match(/^\W*\d+\W*$/) ? parseInt(val) : val;
};

$.focus = function(field) {
    $.field(field).focus();
};

var RATINGS = {
    {{ RATED_GOOD }}: {
        false: "../static/" + "check_blank.png",
        true:  "../static/" + "check_filled.png"
    },
    {{ RATED_BAD }}: {
        prompt: "Please explain how this volunteer performed poorly:",
        false: "../static/" + "lookofdisapproval.jpg",
        true:  "../static/" + "lookofdisapproval_selected.jpg"
    },
    {{ RATED_GREAT }}: {
        prompt: "Please explain how this volunteer went above and beyond:",
        false: "../static/" + "aplus_blank.jpg",
        true:  "../static/" + "aplus_filled.jpg"
    }
};
var renderRating = function(shiftId) {
    var shift = SHIFTS[shiftId];
    var $td = $("#rating" + shiftId).addClass("rating").data("shift", shift);
    $.each([{{ RATED_GOOD }}, {{ RATED_BAD }}, {{ RATED_GREAT }}], function(i, rating) {
        $td.append(
            $("<img/>").attr("src", RATINGS[rating][shift.rating == rating])
                       .attr("title", shift.comment)
                       .data("rating", rating));
    });
};
var setupRatingClickHandler = function() {
    $(document.body).on("click", "td.rating img", function(event) {
        var $img = $(event.target);
        var shift = $img.parent().data("shift");
        var rating = $img.data("rating");
        var comment = "";
        while (!comment && RATINGS[rating].prompt) {
            comment = prompt(RATINGS[rating].prompt);
        }
        $.post("../jobs/rate", {shift_id: shift.id, rating: rating, comment: comment}, function(json) {
            $img.parent().find("img").each(function(){
                var r = $(this).data("rating");
                $(this).attr("title", comment)
                       .attr("src", RATINGS[r][r === rating]);
            });
        }, "json");
    });
};
var setStatus = function(shiftId, status) {
    var $status = $(status);
    $.post("../jobs/set_worked", {id: shiftId, worked: $status.val()}, function(result) {
        $status.parent().empty().append("<i>" + result + "</i> &nbsp; " +
                                        "<a href='../jobs/undo_worked?id=" + shiftId + "'>Undo</a>");
        if ($status.val() == {{ SHIFT_WORKED }}) {
            renderRating(shiftId);
        }
    });
};
