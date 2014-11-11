
function TestCase(title) {
    this.steps = [];
    this.title = title;
    this.completed = false;

    this.context = {};
};

TestCase.prototype.addStep = function(title, f) {
    var s = new TestStep(title, f);
    s.test_case = this;
    this.steps.push(s);
};

TestCase.prototype.repeatStep = function(i) {
    if (i >= this.steps.length) return false;
    var s = this.steps[i];
    this.steps.push(s);
};

TestCase.prototype.run = function(api, events) {
    this.api = api;
    this.events = events;

    this.index = 0;
    this.result = true;
    console.log('Running test-case: ', this.title);
    this.next();
};

TestCase.prototype.next = function() {
    if (this.index < this.steps.length) {
        var s = this.steps[this.index++], that = this;
        console.log(s.title);
        console.log(new Array(80).join('-'));
        s.func();
    } else this.completed = true;
};

TestCase.prototype.fail = function(message) {
    console.error('Test failed: ' + message);
    this.completed = true;
    process.exit(code=1);
};


function TestStep(title, f) {
    this.title = title;
    this.func = f;
};

TestStep.prototype.next = function() {
    setTimeout(this.test_case.next.bind(this.test_case), 10);
    return true;
};

TestStep.prototype.fail = function(msg) {
    return this.test_case.fail(msg);
};


module.exports = TestCase;
