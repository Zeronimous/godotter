
extends Node
func _ready():
    var greeting = tr("Hola GDScript!")
    var item_desc = tr("This is an item: %s" % "Sword")
    var quoted_tip = tr("A \"translated\" tip with new quotes.")
    print(tr("Debug message here."))
